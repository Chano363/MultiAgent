from pathlib import Path

from ato.interface import ATOInterface
from gse.service import get_gse_service

from .atp_interface import ATPInterface
from .dynamics import load_train_config
from .sim_thread import VehicleSimThread
from .vehicle_interface import VehicleSimInterface


class TrainSimulationContext:
    """Runtime objects and immutable configuration for one train."""

    def __init__(
        self,
        train_id: str,
        weight_key: str,
        initial_position_km: float = 0.0,
        direction: str = "up",
    ):
        project_root = Path(__file__).resolve().parents[1]
        dynamics_config = load_train_config(
            project_root=project_root,
            weight_key=weight_key,
            initial_position_km=initial_position_km,
            direction=direction,
        )
        self.static_params = {
            "train_id": train_id,
            "locomotive_type": dynamics_config.locomotive.id,
            "wagon_type": "C80",
            "weight_key": weight_key,
            "total_mass_t": dynamics_config.total_mass_t,
            "wagon_count": dynamics_config.wagon_count,
            "locomotive_count": dynamics_config.locomotive_count,
            "initial_position_km": initial_position_km,
            "direction": direction,
            "train_length_m": dynamics_config.total_length_m,
        }
        self.static_params["loco_type"] = self.static_params["locomotive_type"]
        self.static_params["car_type"] = self.static_params["wagon_type"]
        self.static_params["car_count"] = self.static_params["wagon_count"]

        self.vehicle_interface = VehicleSimInterface(self.static_params, dynamics_config)
        self.gse_service = get_gse_service()
        self.ctc_service = self.gse_service
        self.atp_interface = ATPInterface(self)
        self.ato_interface = ATOInterface(train_id)
        self.sim_thread = VehicleSimThread(self.vehicle_interface, self.atp_interface)
