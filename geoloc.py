__author__ = 'craig'


# geolocation modules
import GeoIP
import IP2Location

# used internally
from netaddr import IPAddress as _IPAddress
from bisect import bisect as _bisect
from collections import defaultdict as _defaultdict




_dbs = {
    'geoip' : None,
    'ip2location' : None,
    'dbip' : None,
    'ipligence' : None
}

# allowable queries to this geolocation service.
supported_queries = ['country_code']

# databases which have currently been loaded and are ready to be queried.
available_dbs = []

def quickload():
    '''
    Loads all known geolocation services using their default filenames from the given working directory.
    Looks in the data folder.
    :param data_dir: directory containing files
    '''
    data_dir = "data"
    load("geoip", data_dir + "/GeoIP.dat")
    load("ip2location", data_dir + "/IP-COUNTRY.bin")
    load("dbip", data_dir + "/dbip-country-2015-07.csv")
    load("ipligence", data_dir + "/ipligence-lite.csv")

def load(db_name, db_fpath):
    '''
    Load a geolocation service.
    :param db_name: name of the geolocation service.
    :param db_fpath: location of its data file.
    '''

    # validate database name
    if db_name not in _dbs.keys(): raise ValueError("Database must be one of: {}".format(_dbs.keys()))

    # load appropriate database
    if db_name == "geoip": _dbs[db_name] = GeoIP.open(db_fpath, GeoIP.GEOIP_STANDARD)
    elif db_name == "ip2location": _dbs[db_name] = IP2Location.IP2Location(db_fpath)
    elif db_name == "dbip": _dbs[db_name] = _loadDBIP(db_fpath)
    elif db_name == "ipligence": _dbs[db_name] = IPligence(db_fpath)
    else: raise ValueError("error loading db {}".format(db_name))

    # update table of supported databases
    global available_dbs
    available_dbs = [k for k,v in _dbs.items() if v is not None]

def clear():
    global _dbs, available_dbs
    _dbs = { k : None for k in _dbs }
    available_dbs = []

def query(to_query, ip_addr, db_name):
    '''
    Query a given database for a property of the address. Use for making lots of
    different kinds of queries.
    :param to_query: attribute to query.
    :param ip_addr: address to lookup.
    :param db_name: name of database to query.
    :return: str result of the query.
    '''
    if to_query not in supported_queries: raise ValueError("Query not supported for {}".format(to_query))
    if to_query == "country_code": return cc(ip_addr, db_name)
    else: raise ValueError("Could not perform {} query in {} database".format(to_query, db_name))

def query_all(to_query, ip_addr, filter_nones=False):
    '''
    Make the given query for every database.
    :param to_query: the field to query.
    :param ip_addr: ip address to lookup.
    :return: { str : str }, database to query result
    '''
    results = { db : query(to_query, ip_addr, db) for db in available_dbs }
    if not filter_nones: return results
    else: return { k : v for k,v in results.items() if v is not None }

def cc(ip_addr, db_name):
    '''
    Query the country code of the ip address from the specified database.
    :param ip_addr: ip address to query
    :param db_name: geolocation db to query from
    :return: country as given by the db. Raises ValueError if db has not yet been created.
    '''

    # validate query
    if db_name not in _dbs.keys(): raise ValueError("Database must be one of: {}".format(_dbs.keys()))
    if _dbs[db_name] is None: raise ValueError("{} has not been created yet (use geoloc.load_db)".format(db_name))

    # perform query
    if db_name == 'geoip': return _dbs[db_name].country_code_by_addr(ip_addr)
    elif db_name == 'ip2location':
        cc = _dbs[db_name].get_country_short(ip_addr)
        return None if cc == '-' else cc
    elif db_name == 'known_networks':
        rt_node = _dbs[db_name].search_best(network=ip_addr, masklen=32)
        return None if rt_node is None else rt_node.data['cc']
    elif db_name == 'dbip': return _dbs[db_name][ip_addr]
    elif db_name == 'ipligence': _dbs[db_name].cc(ip_addr)
    else: raise ValueError("error querying {} db".format(db_name))


def cc_all(ip_addr, filter_nones=False):
    '''
    Query all databases for the country code of the ip address.
    :param ip_addr: ip address to look up
    :param filter_nones: True/False whether to get rid of query results
                which map to None (these mean the database didn't have an entry for that ip)
    :return: { str : str }, a mapping of database -> result
    '''
    results = { db : cc(ip_addr, db) for db in available_dbs }
    if not filter_nones: return results
    else: return { k : v for k,v in results.items() if v is not None }


## Geoloc private/helper functions.
## ----------------------------------------------------------------------

def _loadDBIP(fpath):
    '''
    Load dbip data,
    :param fpath: location of dbip data.
    :return: a dict of ip -> country code.
    '''
    with open(fpath, 'rb') as f:
        values = _defaultdict(lambda : None) # returns None if key not present
        for line in f:
            # line looks like :
            line = line.split(',')
            # every value has quotes around it so strip them
            # also strip end line characters
            values[line[0][1:-1]] = line[2].rstrip()[1:-1]
        return values

    def country_code(me, ip_addr):
        '''
        Query given country code.
        :param ip_addr: address to query.
        :return: str
        '''
        return me.values[ip_addr]



## IPligence wrapper.
## ----------------------------------------------------------------------
class IPligence(object):
    '''
    A wrapper for the IPligence data, which stores country by blocks of
    IP addresses. The ranges are non-overlapping, so we store as a
    monotonically increasing list of elements (store the range by its
    starting point). We keep a mapping of these intervals to their
    country code. To retrieve the CC from a number, we get the index where
    it _would_ be added ala binary search and lookup the mapping for the
    interval in that index.

    e.g. for the intervals [0-9], [10-19], [20-29], our list is:
        [0, 10, 20, 30]
    if we look up 16, binary search will return the index of 20.
    So we go to the left one index, get 10, and look up what 10 maps to.
    The last index is the 'end range'. If something is greater than the
    last element or less than the first element it is out of the range
    represented by this list.
    '''

    def __init__(me, fpath):
        me.intervals = []
        me.mapping = {}

        with open(fpath, 'rb') as f:
            for line in f:

                # stored in .csv file
                line = line.split(',')

                # strip quote marks
                start, end = int(line[0][1:-1]), int(line[1][1:-1])
                cc = line[2][1:-1]

                # no recorded cc for this range
                if len(cc) == 0: continue

                # the data file lists the intervals in ascending order
                # so we can append them straight onto the end and it will be sorted.
                me.intervals.append(start)
                me.mapping[start] = cc

            # store the ending interval for last range
            me.mapping[end] = None

    def cc(me, ip_addr):
        '''
        Look up country code of an address.
        :param ip_addr: ip address to look up.
        '''

        # convert dotted notation to the int representation
        ip_intfmt = int(_IPAddress(ip_addr))

        # out of range of valid IPs
        if ip_intfmt < me.intervals[0] or ip_intfmt > me.intervals[-1]:
            return None

        # use binary search to look up appropriate range
        indx = _bisect(me.intervals, ip_intfmt) - 1
        val = me.intervals[indx]
        return me.mapping[val] if val in me.mapping else None