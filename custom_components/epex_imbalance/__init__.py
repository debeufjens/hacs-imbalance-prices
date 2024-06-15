from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

DOMAIN = "epex_imbalance"


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the EPEX Imbalance Costs component."""
    return True
