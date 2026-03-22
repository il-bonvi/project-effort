"""
CONFIGURATION - Configurazione centralizzata per PEFFORT
Dataclasses con validazione e valori di default
"""

from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class EffortConfig:
    """Configurazione per analisi efforts"""
    window_seconds: int = 60
    merge_power_diff_percent: float = 15
    min_effort_intensity_cp: float = 100
    trim_window_seconds: int = 10
    trim_low_percent: float = 85
    extend_window_seconds: int = 15
    extend_low_percent: float = 80

    def __post_init__(self):
        """Validazione parametri"""
        if self.window_seconds <= 0:
            raise ValueError("window_seconds deve essere > 0")
        if self.merge_power_diff_percent < 0 or self.merge_power_diff_percent > 100:
            raise ValueError("merge_power_diff_percent deve essere 0-100")
        if self.min_effort_intensity_cp < 0 or self.min_effort_intensity_cp > 300:
            raise ValueError("min_effort_intensity_cp deve essere 0-300%")
        if self.trim_window_seconds <= 0:
            raise ValueError("trim_window_seconds deve essere > 0")
        if self.extend_window_seconds <= 0:
            raise ValueError("extend_window_seconds deve essere > 0")


@dataclass
class SprintConfig:
    """Configurazione per analisi sprint"""
    window_seconds: int = 5
    min_power: float = 500
    merge_gap_sec: float = 1.0
    cadence_min_rpm: int = 50

    def __post_init__(self):
        """Validazione parametri"""
        if self.window_seconds <= 0:
            raise ValueError("window_seconds deve essere > 0")
        if self.min_power <= 0:
            raise ValueError("min_power deve essere > 0")
        if self.merge_gap_sec < 0:
            raise ValueError("merge_gap_sec non può essere negativo")
        if self.cadence_min_rpm < 0 or self.cadence_min_rpm > 200:
            raise ValueError("cadence_min_rpm deve essere 0-200 rpm")


@dataclass
class AthleteProfile:
    """Profilo atleta con validazione"""
    cp: float  # Critical Power [W]
    weight: float  # Peso corporeo [kg]
    crank_length: float = 0  # Lunghezza manovella [m] - 0 = disabilitato

    def __post_init__(self):
        """Validazione profilo atleta"""
        if self.cp <= 0 or self.cp > 500:
            raise ValueError(f"CP non valida: {self.cp}. Deve essere tra 1 e 500 W")
        if self.weight <= 0 or self.weight > 200:
            raise ValueError(f"Peso non valido: {self.weight}. Deve essere tra 1 e 200 kg")
        if self.crank_length < 0 or self.crank_length > 0.2:
            raise ValueError(f"Lunghezza manovella non valida: {self.crank_length}. Deve essere tra 0 e 0.2 m")

    @property
    def w_per_kg(self) -> float:
        """Rapporto W/kg al CP"""
        return self.cp / self.weight


@dataclass
class AnalysisConfig:
    """Configurazione globale per analisi"""
    athlete: AthleteProfile
    effort_config: EffortConfig
    sprint_config: SprintConfig

    def validate(self) -> bool:
        """Valida tutte le configurazioni"""
        try:
            # Validazioni sono fatte nei __post_init__ delle sub-config
            logger.info(f"Profilo atleta: {self.athlete.cp}W CP, {self.athlete.weight}kg")
            logger.info(f"Config effort: window={self.effort_config.window_seconds}s, "
                       f"merge={self.effort_config.merge_power_diff_percent}%")
            logger.info(f"Config sprint: window={self.sprint_config.window_seconds}s, "
                       f"min_power={self.sprint_config.min_power}W")
            return True
        except ValueError as e:
            logger.error(f"Errore validazione config: {e}")
            return False

    @staticmethod
    def from_dict(config_dict: dict) -> 'AnalysisConfig':
        """Factory method per creare config da dizionario"""
        athlete = AthleteProfile(
            cp=config_dict.get('cp', config_dict.get('ftp', 280)),
            weight=config_dict.get('weight', 70),
            crank_length=config_dict.get('crank_length', 0) / 1000 if config_dict.get('crank_length', 0) > 0 else 0  # Convert mm to meters
        )
        effort_config = EffortConfig(
            window_seconds=config_dict.get('window_seconds', 60),
            merge_power_diff_percent=config_dict.get('merge_pct', 15),
            min_effort_intensity_cp=config_dict.get('min_cp_pct', config_dict.get('min_ftp_pct', 100)),
            trim_window_seconds=config_dict.get('trim_win', 10),
            trim_low_percent=config_dict.get('trim_low', 85),
            extend_window_seconds=config_dict.get('extend_win', 15),
            extend_low_percent=config_dict.get('extend_low', 80),
        )
        sprint_config = SprintConfig(
            window_seconds=config_dict.get('sprint_window_sec', 5),
            min_power=config_dict.get('min_sprint_power', 500),
            merge_gap_sec=config_dict.get('sprint_merge_gap', 1.0),
            cadence_min_rpm=config_dict.get('cadence_min_rpm', 50)
        )
        return AnalysisConfig(
            athlete=athlete,
            effort_config=effort_config,
            sprint_config=sprint_config
        )
