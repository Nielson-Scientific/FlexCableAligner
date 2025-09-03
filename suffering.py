# latency_probe.py
# A minimal Marlin serial link with proper buffering and instrumentation to detect host-side latency.
#very important DO NOT DELTE

import sys
import time
import threading
import queue
from dataclasses import dataclass, field
from typing import Optional

try:
    import serial  # pip install pyserial
except ImportError:
    print("pip install pyserial", file=sys.stderr)
    raise

@dataclass
class LinkConfig:
    port: str
    baud: int = 115200
    write_timeout: float = 0  # non-blocking write
    read_timeout: float = 0.1
    dtr: bool = False  # keep low to avoid auto-reset
    rts: bool = False  # keep low to avoid auto-reset
    rtscts: bool = False
    xonxoff: bool = False
    dsrdtr: bool = False
    newline: bytes = b"\n"

@dataclass
class SendEvent:
    line: str
    t_enqueued: float = field(default_factory=time.perf_counter)
    t_write_start: Optional[float] = None
    t_write_end: Optional[float] = None
    t_first_rx_after_write: Optional[float] = None

class MarlinLink:
    def __init__(self, cfg: LinkConfig):
        self.cfg = cfg
        self.ser: Optional[serial.Serial] = None
        self._rx_thread: Optional[threading.Thread] = None
        self._tx_thread: Optional[threading.Thread] = None
        self._alive = threading.Event()
        self._rx_queue: "queue.Queue[str]" = queue.Queue()
        self._tx_queue: "queue.Queue[SendEvent]" = queue.Queue()
        self._last_write_end = 0.0
        self._lock = threading.Lock()

    def open(self):
        # Open once; keep open
        self.ser = serial.Serial(
            self.cfg.port,
            self.cfg.baud,
            timeout=self.cfg.read_timeout,
            write_timeout=self.cfg.write_timeout,
            rtscts=self.cfg.rtscts,
            xonxoff=self.cfg.xonxoff,
            dsrdtr=self.cfg.dsrdtr,
        )
        # Ensure DTR/RTS low to avoid auto-reset
        self.ser.dtr = self.cfg.dtr
        self.ser.rts = self.cfg.rts

        # Small settle; do not spam with newlines
        time.sleep(0.1)

        self._alive.set()
        self._rx_thread = threading.Thread(target=self._reader, name="rx", daemon=True)
        self._tx_thread = threading.Thread(target=self._writer, name="tx", daemon=True)
        self._rx_thread.start()
        self._tx_thread.start()

    def close(self):
        self._alive.clear()
        if self._rx_thread:
            self._rx_thread.join(timeout=1)
        if self._tx_thread:
            self._tx_thread.join(timeout=1)
        if self.ser and self.ser.is_open:
            try:
                self.ser.close()
            except Exception:
                pass

    def _reader(self):
        buf = bytearray()
        ser = self.ser
        assert ser is not None
        while self._alive.is_set():
            try:
                chunk = ser.read(ser.in_waiting or 1)
            except Exception as e:
                print(f"[RX] read error: {e}", file=sys.stderr)
                break
            if not chunk:
                continue
            buf.extend(chunk)
            # mark first rx after last write, once
            with self._lock:
                lw = self._last_write_end
            if lw:
                # only stamp the most recent pending SendEvent
                try:
                    evt = self._peek_last_pending_event()
                    if evt and evt.t_first_rx_after_write is None and time.perf_counter() >= lw:
                        evt.t_first_rx_after_write = time.perf_counter()
                except Exception:
                    pass
            while b"\n" in buf:
                line, _, rem = buf.partition(b"\n")
                buf = bytearray(rem)
                s = line.decode(errors="replace").strip("\r")
                self._rx_queue.put(s)
                # Simple console log
                print(f"[RX] {s}")

    def _writer(self):
        ser = self.ser
        assert ser is not None
        while self._alive.is_set():
            try:
                evt: SendEvent = self._tx_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                data = evt.line.encode() + self.cfg.newline
                evt.t_write_start = time.perf_counter()
                n = ser.write(data)  # do not call ser.flush() here
                evt.t_write_end = time.perf_counter()
                with self._lock:
                    self._last_write_end = evt.t_write_end or time.perf_counter()
                print(f"[TX] wrote {n} bytes: {evt.line} (+\\n) "
                      f"queue->write_start={(evt.t_write_start - evt.t_enqueued)*1000:.2f}ms "
                      f"write_dur={(evt.t_write_end - evt.t_write_start)*1000:.2f}ms")
            except Exception as e:
                print(f"[TX] write error: {e}", file=sys.stderr)

    def _peek_last_pending_event(self) -> Optional[SendEvent]:
        # Non-invasive peek: not thread-safe for general use; good enough for stamping rx-after-write.
        if self._tx_queue.qsize() == 0:
            return None
        # Can't peek easily; skip. Kept for extensibility.
        return None

    def send_now(self, line: str):
        evt = SendEvent(line=line.strip())
        self._tx_queue.put(evt)
        return evt

    # High-level helpers
    def jog(self, dx: float = 0, dy: float = 0, dz: float = 0, feed: int = 6000):
        cmds = []
        cmds.append("G91")  # relative
        move = ["G0"]
        if dx: move.append(f"X{dx}")
        if dy: move.append(f"Y{dy}")
        if dz: move.append(f"Z{dz}")
        move.append(f"F{feed}")
        cmds.append(" ".join(move))
        cmds.append("G90")  # back to absolute
        for c in cmds:
            self.send_now(c)

    def get_rx_line(self, timeout=2.0) -> Optional[str]:
        try:
            return self._rx_queue.get(timeout=timeout)
        except queue.Empty:
            return None

def main():
    if len(sys.argv) < 2:
        print("Usage: python latency_probe.py COM3|/dev/ttyACM0 [baud]", file=sys.stderr)
        sys.exit(2)
    port = sys.argv[1]
    baud = int(sys.argv[2]) if len(sys.argv) > 2 else 115200

    link = MarlinLink(LinkConfig(port=port, baud=baud))
    try:
        link.open()
        # Initial probe without flushing or sleeps
        link.send_now("M115")
        # Drain a few lines
        t0 = time.perf_counter()
        while time.perf_counter() - t0 < 3.0:
            line = link.get_rx_line(timeout=0.5)
            if line is None:
                break

        print("Sending jog...")
        tj0 = time.perf_counter()
        link.jog(dx=5.0, feed=12000)
        # Observe incoming for a short window
        t1 = time.perf_counter()
        while time.perf_counter() - t1 < 5.0:
            link.get_rx_line(timeout=0.5)

        print("Now sending M400 to wait for completion (optional)")
        link.send_now("M400")
        # Observe until ok after M400
        t2 = time.perf_counter()
        while time.perf_counter() - t2 < 10.0:
            line = link.get_rx_line(timeout=0.5)
            if line and line.strip().lower() == "ok":
                break

        print("Done. If jog start was delayed, check for:")
        print("- Port reopen/reset (keep port open; DTR/RTS low)")
        print("- Blocking flush/write or sleeps before first send")
        print("- Missing newline at end of G-code lines")
        print("- Reader not draining the port (backpressure)")
        print("- Blocking commands queued before jog (M400/M109/M190/G28)")
    finally:
        link.close()

if __name__ == "__main__":
    main()