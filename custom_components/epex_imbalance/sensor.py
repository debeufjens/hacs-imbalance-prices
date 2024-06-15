import requests
from bs4 import BeautifulSoup
from datetime import datetime, timedelta
import pytz
import voluptuous as vol
import asyncio

from homeassistant.components.sensor import PLATFORM_SCHEMA
from homeassistant.const import CONF_NAME, ATTR_ATTRIBUTION
from homeassistant.helpers.entity import Entity
import homeassistant.helpers.config_validation as cv

DEFAULT_NAME = "EPEX Imbalance Costs"

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Optional(CONF_NAME, default=DEFAULT_NAME): cv.string,
    }
)


def fetch_imbalance_costs():
    url = "https://opendata.elia.be/api/explore/v2.1/catalog/datasets/ods136/records"
    params = {
        "limit": 1,
        "sort": "-datetime",
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()

        if "results" in data and data["results"]:
            record = data["results"][0]
            imbalance_costs = record.get("predictions_silinearregressionforecast")

            if imbalance_costs is not None:
                return imbalance_costs
            else:
                return 0
        else:
            return 0

    except requests.exceptions.RequestException:
        return 0


def get_dynamic_url():
    today = datetime.today()
    trading_date = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    delivery_date = today.strftime("%Y-%m-%d")
    url = (
        f"https://www.epexspot.com/en/market-data?market_area=BE&auction=IDA1&"
        f"trading_date={trading_date}&delivery_date={delivery_date}&underlying_year=&"
        f"modality=Auction&sub_modality=Intraday&technology=&data_mode=table&period=&"
        f"production_period="
    )
    return url


def fetch_epexspot_prices():
    url = get_dynamic_url()

    try:
        response = requests.get(url)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")
        brussels_tz = pytz.timezone("Europe/Brussels")
        current_time = datetime.now(brussels_tz).strftime("%H:%M")

        times_list = soup.find("div", {"class": "fixed-column js-table-times"})
        prices_table = soup.find("table", {"class": "table-01 table-length-1"})

        if not times_list or not prices_table:
            return None

        times = [li.text.strip() for li in times_list.find_all("li")]

        prices = []
        rows = prices_table.find_all("tr")[3:]

        for row in rows:
            cells = row.find_all("td")
            if len(cells) > 3:
                price = cells[3].text.strip().replace("€/MWh", "").replace(",", ".")
                prices.append(float(price))

        matched_price = None
        for time_range, price in zip(times, prices):
            start_time_str, end_time_str = time_range.split(" - ")
            start_time = datetime.strptime(start_time_str, "%H:%M").time()
            end_time = datetime.strptime(end_time_str, "%H:%M").time()
            current_time_obj = datetime.strptime(current_time, "%H:%M").time()

            if start_time <= current_time_obj < end_time:
                matched_price = price
                break

        return matched_price

    except requests.exceptions.RequestException:
        return None
    except ValueError:
        return None


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    name = config.get(CONF_NAME)
    sensor = EPEXImbalanceSensor(name)
    async_add_entities([sensor], True)

    async def update_sensor(now):
        await sensor.async_update_ha_state(True)
        schedule_next_update(now)

    def schedule_next_update(now):
        next_update = (now + timedelta(minutes=15)).replace(second=0, microsecond=0)
        next_update_1 = next_update + timedelta(minutes=1)
        next_update_7 = next_update + timedelta(minutes=7)

        hass.helpers.event.async_track_point_in_time(update_sensor, next_update_1)
        hass.helpers.event.async_track_point_in_time(update_sensor, next_update_7)

    now = datetime.now()
    schedule_next_update(now)


class EPEXImbalanceSensor(Entity):

    def __init__(self, name):
        self._name = name
        self._state = None
        self._attributes = {}

    @property
    def name(self):
        return self._name

    @property
    def state(self):
        return self._state

    @property
    def extra_state_attributes(self):
        return self._attributes

    async def async_update(self):
        imbalance_costs = fetch_imbalance_costs()
        epex_prices = fetch_epexspot_prices()

        if epex_prices is not None:
            total_price = epex_prices + imbalance_costs
            self._state = total_price
            self._attributes = {
                "EPEX Price": epex_prices,
                "Imbalance Costs": imbalance_costs,
                "Total Price": total_price,
            }
        else:
            self._state = None
            self._attributes = {}
