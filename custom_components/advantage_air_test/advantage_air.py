import json
import asyncio
import aiohttp
import collections.abc
import xmltodict


def update(d, u):
    for k, v in u.items():
        if isinstance(v, collections.abc.Mapping):
            d[k] = update(d.get(k, {}), v)
        else:
            d[k] = v
    return d


class ApiError(Exception):
    """AdvantageAir Error"""


class advantage_air:
    """AdvantageAir Connection"""

    def __init__(self, ip, port=2025, session=None, retry=5):

        if session is None:
            session = aiohttp.ClientSession()

        self.ip = ip
        self.port = port
        self.session = session
        self.retry = retry
        
        self.aircon = self.advantage_air_endpoint(ip,port,session,retry,False,"setAircon")
        self.lights = self.advantage_air_endpoint(ip,port,session,retry,False,"setLight")
        self.things = self.advantage_air_endpoint(ip,port,session,retry,False,"setThing")

    async def async_get(self, retry=None):
        retry = retry or self.retry
        data = {}
        count = 0
        error = None
        while count < retry:
            count += 1
            try:
                ## peek to see if this is the authenticated XML API
                async with self.session.get(
                    f"http://{self.ip}:{self.port}/getSystemData",
                    timeout=aiohttp.ClientTimeout(total=4),
                ) as resp:
                    assert resp.status == 200
                    body = await resp.content.read()

                ## Check if the response is XML, if so we need to do some extra processing as this is the older Myair variant
                if body.decode("utf-8").startswith(f"<?xml"):
                    self.aircon = self.advantage_air_endpoint(self.ip,self.port,self.session,self.retry,True,"setAircon")
                    self.isxml = True
                    system_xml = xmltodict.parse(body)

                    ## if not authenticated, then perform the login.. and request the system data again
                    if system_xml.get("iZS10.3").get("authenticated") == '0':
                        async with self.session.get(
                            f"http://{self.ip}:{self.port}/login?password=password",
                            timeout=aiohttp.ClientTimeout(total=4),
                        ) as resp:
                            assert resp.status == 200
                            body = await resp.content.read()
                            login_xml = xmltodict.parse(body)

                        assert login_xml.get("iZS10.3").get("authenticated") == '1'

                        ## logged in, now get the full system data
                        async with self.session.get(
                            f"http://{self.ip}:{self.port}/getSystemData",
                            timeout=aiohttp.ClientTimeout(total=4),
                        ) as resp:
                            assert resp.status == 200
                            body = await resp.content.read()
                            system_xml = xmltodict.parse(body)

                    async with self.session.get(
                        f"http://{self.ip}:{self.port}/getZoneData?zone=*",
                        timeout=aiohttp.ClientTimeout(total=4),
                    ) as resp:
                        assert resp.status == 200
                        body = await resp.content.read()
                        zone_xml = xmltodict.parse(body)

                    ## now build up a json structure compatible withe the current code

                    def fanspeed(numval):
                        if numval == "3":
                            return "high"
                        elif numval == "2":
                            return "medium"
                        elif numval == "1":
                            return "low"

                    def acmode(numval):
                        if numval == "3":
                            return "vent"
                        elif numval == "2":
                            return "heat"
                        elif numval == "1":
                            return "cool"
                    
                    def acstate(numval):
                        if numval == '1':
                            return "on"
                        elif numval == '0':
                            return "off"

                    def acerror(motor, battery):
                        if motor == "1" or battery == "1":
                            return 1
                        else:
                            return 0


                    def zonestate(setting):
                        if setting == "0":
                            return "closed"
                        else:
                            return "open"

                    ac_data = { "info": 
                        {
                            "climateControlModeIsRunning": False,
                            "countDownToOff": 0,
                            "countDownToOn": 0,
                            "fan": f"""{fanspeed(system_xml.get("iZS10.3").get("system").get("unitcontrol").get("fanSpeed"))}""",
                            "filterCleanStatus": 0,
                            "freshAirStatus": "off",
                            "mode": f"""{acmode(system_xml.get("iZS10.3").get("system").get("unitcontrol").get("mode"))}""",
                            "myZone": int(system_xml.get("iZS10.3").get("system").get("unitcontrol").get("unitControlTempsSetting")),
                            "name": f"""{system_xml.get("iZS10.3").get("system").get("name")}""",
                            "setTemp": int(float(system_xml.get("iZS10.3").get("system").get("unitcontrol").get("centralDesiredTemp"))),
                            "state": f"""{acstate(system_xml.get("iZS10.3").get("system").get("unitcontrol").get("airconOnOff"))}"""

                        }
                    }

                    num_zones = int(system_xml.get("iZS10.3").get("system").get("unitcontrol").get("numberOfZones"))

                    zone_data = {}
                    for zone in range(num_zones):

                        src_index = f"zone{zone+1}"
                        zone_data |= { 
                            f"z0{zone+1}": 
                            {
                                "error": acerror(zone_xml.get("iZS10.3").get(src_index).get("hasMotorError"),zone_xml.get("iZS10.3").get(src_index).get("hasLowBatt")),
                                "maxDamper": int(zone_xml.get("iZS10.3").get(src_index).get("maxDamper")),
                                "measuredTemp": int(float(zone_xml.get("iZS10.3").get(src_index).get("actualTemp"))),
                                "minDamper": int(zone_xml.get("iZS10.3").get(src_index).get("minDamper")),
                                "motion": 0,
                                "motionConfig": 0,
                                "name": f"""{zone_xml.get("iZS10.3").get(src_index).get("name")}""",
                                "number": zone+1,
                                "rssi": int(zone_xml.get("iZS10.3").get(src_index).get("RFstrength")),
                                "setTemp": int(float(zone_xml.get("iZS10.3").get(src_index).get("desiredTemp"))),
                                "state": zonestate(zone_xml.get("iZS10.3").get(src_index).get("setting")),
                                "type": 1,
                                "value": int(zone_xml.get("iZS10.3").get(src_index).get("userPercentSetting"))
                            }
                        }

                    ac_data |= { "zones": zone_data }

                    data = { 
                        "aircons": 
                            { 
                                "ac1": ac_data 
                            },
                        "system": {
                            "hasAircons": True,
                            "hasLights": False,
                            "hasSensors": False,
                            "hasThings": False,
                            "hasThingsBOG": False,
                            "hasThingsLight": False,
                            "needsUpdate": False,
                            "name": f"""{system_xml.get("iZS10.3").get("system").get("name")}""",
                            "rid": f"""{system_xml.get("iZS10.3").get("mac")}""",
                            "sysType": "e-zone",
                            "myAppRev": f"""{system_xml.get("iZS10.3").get("system").get("MyAppRev")}"""
                        }
                    }
                    return data

                else:    ## This is the current (standard) JSON API...
                    self.isxml = False
                    async with self.session.get(
                        f"http://{self.ip}:{self.port}/getSystemData",
                        timeout=aiohttp.ClientTimeout(total=4),
                    ) as resp:
                        assert resp.status == 200
                        data = await resp.json(content_type=None)
                    if "aircons" in data:
                        return data
            except (
                aiohttp.ClientError, 
                aiohttp.ClientConnectorError, 
                aiohttp.client_exceptions.ServerDisconnectedError, 
                ConnectionResetError,
            ) as err:
                error = err
                break
            except asyncio.TimeoutError:
                error = "Connection timed out."
                break
            except AssertionError:
                error = "Response status not 200."
                break
            except SyntaxError as err:
                error = "Invalid response"
                break

            await asyncio.sleep(1)
        raise ApiError(
            f"No valid response after {count} failed attempt{['','s'][count>1]}. Last error was: {error}"
        )

    class advantage_air_endpoint:
        
        def __init__(self, ip, port, session, retry, isxml, endpoint):
            self.ip = ip
            self.port = port
            self.session = session
            self.retry = retry
            self.endpoint = endpoint
            self.changes = {}
            self.isxml = isxml
            self.lock = asyncio.Lock()

        async def async_set(self, change):

            ## Send requests with the old XML API            
            async def async_set_xml(endpoint, querystring):
                async with self.session.get(f"http://{self.ip}:{self.port}/{endpoint}?{querystring}",
                    timeout=aiohttp.ClientTimeout(total=4),
                ) as resp:
                    if resp.status != 200:
                        raise ApiError("HTTP error")
                    body = await resp.content.read()
                    resp_xml = xmltodict.parse(body)
                    if resp_xml.get('iZS10.3') == None or resp_xml['iZS10.3'].get('ack') != '1':
                        raise ApiError("API error")

            """Merge changes with queue and send when possible, returning True when done"""
            
            self.changes = update(self.changes, change)
            if self.lock.locked():
                return False
            async with self.lock:
                while self.changes:
                    # Allow any addition changes from the event loop to be collected
                    await asyncio.sleep(0)
                    # Collect all changes
                    payload = self.changes
                    self.changes = {}
                    try:
                        if (self.isxml):
                            ## change to system wide setting
                            if payload.get('ac1').get('info') != None:

                                ## change main temp 
                                value = payload.get('ac1').get('info').get('setTemp')
                                if value != None:
                                    await async_set_xml("setSystemData", f"""centralDesiredTemp={value}""")

                                ## change the myzone 
                                value = payload.get('ac1').get('info').get('myZone')
                                if value != None:
                                    await async_set_xml("setSystemData", f"""unitControlTempsSetting={value}""")


                                ## change main on/off 
                                strvalue = payload.get('ac1').get('info').get('state')
                                if strvalue != None:
                                    if strvalue == 'on':
                                        value = 1
                                    elif strvalue == 'off':
                                        value = 0
                                    await async_set_xml("setSystemData", f"""airconOnOff={value}""")

                                ## change the mode  heat, cool, vent
                                strvalue = payload.get('ac1').get('info').get('mode')
                                if strvalue != None:
                                    if strvalue == 'heat':
                                        value = 2
                                    elif strvalue == 'cool':
                                        value = 1
                                    elif strvalue == 'vent':
                                        value = 3
                                    await async_set_xml("setSystemData", f"""mode={value}""")

                                ## change the fan autoAA, high, medium, low 
                                strvalue = payload.get('ac1').get('info').get('fan')
                                if strvalue != None:
                                    if strvalue == 'autoAA' or strvalue == "high":
                                        value = 3
                                    elif strvalue == 'medium':
                                        value = 2
                                    elif strvalue == 'low':
                                        value = 1
                                    await async_set_xml("setSystemData", f"""fanSpeed={value}""")

                            ## change to zone wide setting
                            if change.get('ac1').get('zones') != None:
                                for strzone in payload['ac1']['zones'].keys():
                                    zone = int(strzone[1:3])

                                    value = payload['ac1']['zones'][strzone].get('setTemp')
                                    if value != None:
                                        await async_set_xml("setZoneData", f"""zone={zone}&desiredTemp={value}""")
                                        
                                    strvalue = payload['ac1']['zones'][strzone].get('state')
                                    if strvalue != None:
                                        if strvalue == "open":
                                            value = 1
                                        elif strvalue == "close":
                                            value = 0
                                        await async_set_xml("setZoneData", f"""zone={zone}&zoneSetting={value}""")
                        else:
                            async with self.session.get(
                                f"http://{self.ip}:{self.port}/{self.endpoint}",
                                params={"json": json.dumps(payload)},
                                timeout=aiohttp.ClientTimeout(total=4),
                            ) as resp:
                                data = await resp.json(content_type=None)
                            if data["ack"] == False:
                                raise ApiError(data["reason"])
                    except (
                        aiohttp.client_exceptions.ServerDisconnectedError, 
                        ConnectionResetError,
                    ) as err:
                        # Recoverable error, reinsert the changes and try again in a second
                        self.changes = update(self.changes, payload)
                        await asyncio.sleep(1)
                    except aiohttp.ClientError as err:
                        raise ApiError(err)
                    except asyncio.TimeoutError:
                        raise ApiError("Connection timed out.")
                    except AssertionError:
                        raise ApiError("Response status not 200.")
                    except SyntaxError as err:
                        raise ApiError("Invalid response")
            return True
