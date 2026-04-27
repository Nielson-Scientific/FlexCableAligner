
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Optional
from queue import Queue

from utils.AutoFocus import Autofocus as AF


class CameraControlError(RuntimeError):
	pass


@dataclass(frozen=True)
class CameraFrame:
	image_bgr: "object"  # numpy ndarray, kept generic to avoid hard dependency here
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
		try:
			image = self._frame_queue.get_nowait()
			return CameraFrame(image_bgr=image, timestamp_s=time.time())
		except Exception:
			return None
		# with self._frame_lock:
		# 	return self._latest_frame

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

		try:
			stream = cam.get_streams()[0]
			stream.GVSPAdjustPacketSize.run()
			while not stream.GVSPAdjustPacketSize.is_done():
				pass
		except Exception:
			pass

	def _setup_pixel_format(self, cam) -> None:
		from vmbpy import (
			COLOR_PIXEL_FORMATS,
			MONO_PIXEL_FORMATS,
			PixelFormat,
			intersect_pixel_formats,
		)

		opencv_display_format = PixelFormat.Bgr8

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
				"Camera does not support an OpenCV compatible pixel format (Bgr8 convertible)."
			)

	def _handler(self, cam, stream, frame) -> None:
		from vmbpy import FrameStatus, PixelFormat

		if frame.get_status() == FrameStatus.Complete:
			try:
				if frame.get_pixel_format() == PixelFormat.Bgr8:
					display = frame
				else:
					display = frame.convert_pixel_format(PixelFormat.Bgr8)

				image = display.as_opencv_image()
				self._handler_helper(image)
				self._frame_queue.put_nowait(image)
				# with self._frame_lock:
				# 	self._latest_frame = CameraFrame(image_bgr=image, timestamp_s=time.time())
			except Exception:
				pass

		try:
			cam.queue_frame(frame)
		except Exception:
			pass
	
	def _handler_helper(self, image):
		pass

	def register_handler_helper(self, func):
		_handler_helper = func
		

if __name__ == "__main__":
	UP_TIME = 1
	RESTART_TIME = 5
	print('Creating CameraControl instance')
	c = CameraControl("DEV_1AB22C071903")
	print('CameraControl instance created')\
	
	def helper(image):
		AF.test_capture_image(image)
		print(f"Sharpness Score: {AF.get_sharpness_score(image)}")
	c.register_handler_helper(helper)


	print('Starting camera feed')
	c.start()
	print(f'Camera feed started, sleeping for {UP_TIME} seconds')
	time.sleep(UP_TIME)
	print('Stopping camera feed')
	c.get_latest_frame()
	c.restart()
	print(f'Camera feed restarted, sleeping for {RESTART_TIME} seconds')
	c.stop()