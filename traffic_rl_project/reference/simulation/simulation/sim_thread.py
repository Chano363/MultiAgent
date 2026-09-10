# simulation/sim_thread.py

from PySide6.QtCore import QThread
import time

from .vehicle_interface import VehicleSimInterface
from .atp_interface import ATPInterface


class VehicleSimThread(QThread):
    """
    独立仿真线程：
    - 周期性调用 VehicleSimInterface.step(dt)
    - 将状态传递给 ATPInterface
    """

    def __init__(
        self,
        vehicle_interface: VehicleSimInterface,
        atp_interface: ATPInterface,
        parent=None,
        time_scale: float = 1.0,
    ):
        super().__init__(parent)
        self.vehicle_interface = vehicle_interface
        self.atp_interface = atp_interface
        self._running = True
        self._paused = False
        self._wall_dt = 0.1  # 100 ms UI/state update cadence.
        self._time_scale = time_scale

    def run(self):
        self.vehicle_interface.start()
        while self._running:
            cycle_started = time.perf_counter()
            if not self._paused:
                sim_dt = self._wall_dt * self._time_scale
                state = self.vehicle_interface.step(sim_dt, emit_signal=False)
                self.atp_interface.update_from_state(state)
                self.vehicle_interface.publish_state()
            elapsed = time.perf_counter() - cycle_started
            time.sleep(max(0.0, self._wall_dt - elapsed))

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def stop(self):
        self._running = False
        self.vehicle_interface.stop()
        self.quit()
        self.wait()
