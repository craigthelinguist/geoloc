__author__ = 'craig'

import GeoIP
import IP2Location

_dbs = {
    'geoip' : None,
    'ip2location' : None
}

def quickload(data_dir):
    '''
    Loads all known geolocation services using their default filenames from the given working directory.
    :param data_dir: directory containing files
    '''
    load_db("geoip", data_dir + "/GeoIP.dat")
    load_db("ip2location", data_dir + "/IP-COUNTRY.bin")

def load_db(db_name, db_fpath):
    '''
    Load a geolocation service.
    :param db_name: name of the geolocation service.
    :param db_fpath: location of its data file.
    '''
    if db_name not in _dbs.keys(): raise ValueError("Database must be one of: {}".format(_dbs.keys()))
    if db_name == "geoip": _dbs[db_name] = GeoIP.open(db_fpath, GeoIP.GEOIP_STANDARD)
    elif db_name == "ip2location": _dbs[db_name] = IP2Location.IP2Location(db_fpath)
    else: raise ValueError("error loading db {}".format(db_name))

def available_dbs():
    '''
    Get a list of available dbs by name.
    :return: list of strings
    '''
    return [x for x in _dbs.keys() if _dbs[x] is not None]

def country_code(ip_addr, db_name):
    '''
    Query the country code of the ip address from the specified database.
    :param ip_addr: ip address to query
    :param db_name: geolocation db to query from
    :return: country as given by the db. Raises ValueError if db has not yet been created.
    '''
    if db_name not in _dbs.keys(): raise ValueError("Database must be one of: {}".format(_dbs.keys()))
    if _dbs[db_name] is None: raise ValueError("{} has not been created yet (use geoloc.load_db)".format(db_name))
    if db_name == 'geoip': return _dbs[db_name].country_code_by_addr(ip_addr)
    elif db_name == 'ip2location': return _dbs[db_name].get_country_short(ip_addr)
    else: raise ValueError("error querying {} db".format(db_name))