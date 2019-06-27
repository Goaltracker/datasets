# -*- coding: utf-8 -*-

import glob
import os
import os.path as osp
import requests as req
from multiprocessing import Pool
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from functools import partial


API_BASE = "https://unstats.un.org"


def cleanup_source():
    for f in glob.glob("../source/*csv"):
        os.remove(f)


# from https://www.peterbe.com/plog/best-practice-with-retries-with-requests
def requests_retry_session(
    retries=5,
    backoff_factor=0.3,
    status_forcelist=(500, 502, 504),
    session=None,
):
    session = session or req.Session()
    retry = Retry(
        total=retries,
        read=retries,
        connect=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session


def api_path(api_base, *args):
    res = api_base
    for arg in args:
        if arg.startswith('/'):
            res = osp.join(res, arg[1:])
        else:
            res = osp.join(res, arg)
    return res


def get_all_series():
    j = req.get(api_path(API_BASE, "/SDGAPI", "/v1/sdg/Series/List"), params={'allreleases': False}).json()
    return j


def download(v, csv_api):
    code = v['code']

    f = f'../source/{code}.csv'
    csv = requests_retry_session().post(csv_api, data={'seriesCodes': code}, stream=True, timeout=60)

    with open(f'../source/{code}.csv', 'wb') as f:
        for chunk in csv.iter_content(chunk_size=1024):
            f.write(chunk)
            f.flush()


def main():
    all_ser = get_all_series()
    csv_api = api_path(API_BASE, "/SDGAPI", "/v1/sdg/Series/DataCSV")

    download_ = partial(download, csv_api=csv_api)

    with Pool(5) as p:
        p.map(download_, all_ser)


if __name__ == '__main__':
    cleanup_source()
    main()
    print('Done.')
