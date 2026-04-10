
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional
from queue import Queue


class CameraControlError(RuntimeError):
	pass


@dataclass(frozen=True)
class CameraFrame:
	image_rgb: "object"  # numpy ndarray, kept generic to avoid hard dependency here
	timestamp_s: float


class CameraControl:
	"""Wraps Vimba/vmbpy streaming for a single camera and keeps the latest frame."""

	_vmb_lock = threading.Lock()
	_vmb_refcount = 0
	_vmb_instance = None

	def __init__(
		self,
		camera_id: str,
		*,
		buffer_count: int = 10,
	):
		if camera_id is None or not str(camera_id).strip():
			raise CameraControlError(
				"camera_id is required (fill in CAMERA_1_ID/CAMERA_2_ID in WebInterface.py)"
			)

		self.camera_id = str(camera_id).strip()
		self.buffer_count = int(buffer_count)

		self._cam = None
		self._running = False
		self._vmb_acquired = False
		self._frame_lock = threading.Lock()
		self._latest_frame: Optional[CameraFrame] = None
		self._frame_queue = Queue(maxsize=buffer_count)

	@property
	def is_running(self) -> bool:
		return self._running

	def get_latest_frame(self) -> Optional[CameraFrame]:
		# try:
		# 	image = self._frame_queue.get_nowait()
		# 	return CameraFrame(image_rgb=image, timestamp_s=time.time())
		# except Exception:
		# 	return None
		with self._frame_lock:
			return self._latest_frame

	def start(self) -> None:
		if self._running:
			return

		try:
			vmb = self._acquire_vmb()
			self._vmb_acquired = True
			cam = vmb.get_camera_by_id(self.camera_id)

			cam.__enter__()
			self._cam = cam

			self._setup_camera(cam)
			self._setup_pixel_format(cam)

			cam.start_streaming(handler=self._handler, buffer_count=self.buffer_count)
			self._running = True
		except Exception:
			try:
				self.stop()
			except Exception:
				pass
			raise

	def stop(self) -> None:
		if self._cam is None:
			self._running = False
			if self._vmb_acquired:
				self._vmb_acquired = False
				self._release_vmb_if_needed()
			return

		cam = self._cam
		self._cam = None
		try:
			try:
				cam.stop_streaming()
			except Exception:
				pass
		finally:
			try:
				cam.__exit__(None, None, None)
			except Exception:
				pass

			self._running = False
			if self._vmb_acquired:
				self._vmb_acquired = False
				self._release_vmb_if_needed()

	def restart(self) -> None:
		self.stop()
		self.start()

	# ------------------------
	# vmbpy internals
	# ------------------------
	@classmethod
	def _acquire_vmb(cls):
		try:
			from vmbpy import VmbSystem
		except Exception as exc:  # pragma: no cover
			raise CameraControlError(
				"vmbpy is not available in this environment. Install/enable vmbpy before starting feeds."
			) from exc

		with cls._vmb_lock:
			if cls._vmb_refcount == 0:
				cls._vmb_instance = VmbSystem.get_instance()
				cls._vmb_instance.__enter__()
			cls._vmb_refcount += 1
			return cls._vmb_instance

	@classmethod
	def _release_vmb_if_needed(cls) -> None:
		with cls._vmb_lock:
			if cls._vmb_refcount <= 0:
				cls._vmb_refcount = 0
				return

			cls._vmb_refcount -= 1
			if cls._vmb_refcount == 0 and cls._vmb_instance is not None:
				try:
					cls._vmb_instance.__exit__(None, None, None)
				finally:
					cls._vmb_instance = None

	def _setup_camera(self, cam) -> None:
		try:
			cam.ExposureAuto.set("Continuous")
		except Exception:
			pass

		try:
			cam.BalanceWhiteAuto.set("Continuous")
		except Exception:
			pass

		self._setup_resolution(cam)

		try:
			stream = cam.get_streams()[0]
			stream.GVSPAdjustPacketSize.run()
			while not stream.GVSPAdjustPacketSize.is_done():
				pass
		except Exception:
			pass

	def _setup_resolution(self, cam, width: int = 1920, height: int = 1080) -> None:
		"""Constrain the camera output to at most *width* x *height* (1080p by default).

		If the sensor is smaller than the requested size the camera runs at its native
		resolution.  Offsets are centred so we capture the middle of the sensor.
		"""
		try:
			# Reset offsets to 0 first so Width/Height changes are never out-of-range.
			try:
				cam.OffsetX.set(0)
			except Exception:
				pass
			try:
				cam.OffsetY.set(0)
			except Exception:
				pass

			# Clamp to whatever the sensor can actually deliver.
			target_w = min(width, cam.Width.get_range()[1])
			target_h = min(height, cam.Height.get_range()[1])

			# Width/Height must be multiples of their increment (usually 1 or 2).
			try:
				w_inc = cam.Width.get_increment()
				target_w = (target_w // w_inc) * w_inc
			except Exception:
				pass
			try:
				h_inc = cam.Height.get_increment()
				target_h = (target_h // h_inc) * h_inc
			except Exception:
				pass

			cam.Width.set(target_w)
			cam.Height.set(target_h)

			# Centre the ROI on the sensor.
			try:
				sensor_w = cam.SensorWidth.get()
				offset_x = max(0, (sensor_w - target_w) // 2)
				try:
					x_inc = cam.OffsetX.get_increment()
					offset_x = (offset_x // x_inc) * x_inc
				except Exception:
					pass
				cam.OffsetX.set(offset_x)
			except Exception:
				pass

			try:
				sensor_h = cam.SensorHeight.get()
				offset_y = max(0, (sensor_h - target_h) // 2)
				try:
					y_inc = cam.OffsetY.get_increment()
					offset_y = (offset_y // y_inc) * y_inc
				except Exception:
					pass
				cam.OffsetY.set(offset_y)
			except Exception:
				pass

		except Exception:
			# Non-fatal: fall back to native resolution if anything goes wrong.
			pass

	def _setup_pixel_format(self, cam) -> None:
		from vmbpy import (
			COLOR_PIXEL_FORMATS,
			MONO_PIXEL_FORMATS,
			PixelFormat,
			intersect_pixel_formats,
		)

		opencv_display_format = PixelFormat.Rgb8

		cam_formats = cam.get_pixel_formats()
		cam_color_formats = intersect_pixel_formats(cam_formats, COLOR_PIXEL_FORMATS)
		convertible_color_formats = tuple(
			f
			for f in cam_color_formats
			if opencv_display_format in f.get_convertible_formats()
		)

		cam_mono_formats = intersect_pixel_formats(cam_formats, MONO_PIXEL_FORMATS)
		convertible_mono_formats = tuple(
			f
			for f in cam_mono_formats
			if opencv_display_format in f.get_convertible_formats()
		)

		if opencv_display_format in cam_formats:
			cam.set_pixel_format(opencv_display_format)
		elif convertible_color_formats:
			cam.set_pixel_format(convertible_color_formats[0])
		elif convertible_mono_formats:
			cam.set_pixel_format(convertible_mono_formats[0])
		else:
			raise CameraControlError(
				"Camera does not support an OpenCV compatible pixel format (Rgb8 convertible)."
			)

	def _handler(self, cam, stream, frame) -> None:
		from vmbpy import FrameStatus, PixelFormat

		if frame.get_status() == FrameStatus.Complete:
			try:
				if frame.get_pixel_format() == PixelFormat.Rgb8:
					display = frame
				else:
					display = frame.convert_pixel_format(PixelFormat.Rgb8)

				image = display.as_opencv_image()
				# self._frame_queue.put_nowait(image)
				with self._frame_lock:
					self._latest_frame = CameraFrame(image_rgb=image, timestamp_s=time.time())
			except Exception:
				pass

		try:
			cam.queue_frame(frame)
		except Exception:
			pass

if __name__ == "__main__":
	print('Creating CameraControl instance')
	c = CameraControl("DEV_1AB22C071903")
	print('CameraControl instance created')
	print('Starting camera feed')
	c.start()
	print('Camera feed started, sleeping for 5 seconds')
	time.sleep(5)
	print('Stopping camera feed')
	c.get_latest_frame()
	c.restart()
	print('Camera feed restarted, sleeping for 5 seconds')
	c.stop()