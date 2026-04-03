from vmbpy import *
import sys
from typing import Optional

def abort(reason: str, return_code: int = 1, usage: bool = False):
    print(reason + '\n')
    sys.exit(return_code)


class VimbaCameraControl:
    def __init__(self, camera_id: Optional[str] = None):
        self.instance = VmbSystem.get_instance()
        self.camera = self.get_camera(camera_id)
        print(f"Using camera: {self.camera.get_id()} - {self.camera.get_name()}")
        self.setup_camera(self.camera)

    def get_frames(self):
        with self.camera:
            for frame in self.camera.get_frame_generator(limit=10, timeout_ms=3000):
                print('Got frame')

    def setup_camera(self, cam: Camera):
        with cam:
            # Try to adjust GeV packet size. This Feature is only available for GigE - Cameras.
            try:
                stream: Stream = cam.get_streams()[0]
                stream.GVSPAdjustPacketSize.run()
                while not stream.GVSPAdjustPacketSize.is_done():
                    pass

            except (AttributeError, VmbFeatureError):
                pass

    def get_camera(self, camera_id: Optional[str]) -> Camera:
        with VmbSystem.get_instance() as vmb:
            if camera_id:
                try:
                    return vmb.get_camera_by_id(camera_id)

                except VmbCameraError:
                    abort('Failed to access Camera \'{}\'. Abort.'.format(camera_id))

            else:
                cams = vmb.get_all_cameras()
                if not cams:
                    abort('No Cameras accessible. Abort.')

                return cams[0]
            
if __name__ == "__main__":
    camera_control = VimbaCameraControl()
    camera_control.get_frames()