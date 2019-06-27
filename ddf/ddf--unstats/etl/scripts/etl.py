# -*- coding: utf-8 -*-

import os

import pandas as pd
import numpy as np
import requests as req

from pandas.api.types import is_numeric_dtype
from ddf_utils.str import to_concept_id, format_float_digits
from ddf_utils.chef.helpers import sort_df
from functools import partial
from update_source import api_path, API_BASE, get_all_series


FORMATTER = partial(format_float_digits, digits=7)


def read_source(name):
    try:
        return pd.read_csv(f'../source/{name}.csv', thousands=',').dropna(how='all')
    except pd.errors.EmptyDataError:
        return None


def get_key_columns(df):
    res = ['GeoAreaCode', 'TimePeriod']
    for c in df.columns:
        if c == '[Reporting Type]':
            continue
        if c.startswith('['):  # dimensions were quoted by brackets in source
            res.append(c)

    return res


def create_entity(concept, vec):
    ids = list(map(to_concept_id, vec))
    return pd.DataFrame({concept: ids, 'name': vec})


def check_source(df, key_columns):
    # for series that appeared in multiple goals, only keep one.
    if len(df.Indicator.unique()) > 1:
        df = df[df.Indicator == df.Indicator.values[0]]

    if df.duplicated(subset=key_columns).any():
        print("duplicated datapoints.")
        print(df.columns)

    for k in key_columns:
        if df[k].hasnans:
            print("column {} has NaNs".format(k))
            if k == 'TimePeriod':
                # if timePeriod is N/A, we will just drop it
                df = df.dropna(subset=['TimePeriod'])
            else:
                # otherwise we fillna with new value
                df[k] = df[k].fillna("NOTSPEC")

    return df


def serve_datapoints(df, concept=None):
    """save a dataframe to disk, with DDF naming. Assume primaryKeys are
    in front of measure column.
    """
    if not concept:
        by_lst = sorted(df.columns[:-1])
        by = '--'.join(by_lst)
        concept = df.columns[-1]
    else:
        by_lst = sorted(list(filter(lambda x: x != concept, df.columns)))
        by = '--'.join(by_lst)

    if df['geo_area'].dtype != np.int:
        df['geo_area'] = df['geo_area'].map(lambda x: int(x))

    if df['year'].dtype != np.int:
        df['year'] = df['year'].map(lambda x: int(x))

    if not is_numeric_dtype(df[concept]):
        print("\tnot numeric data")
    else:
        df[concept] = df[concept].map(FORMATTER)

    # sort dataframe and remove NaNs
    df = df.dropna(subset=[concept])
    df = sort_df(df, by_lst)

    df.to_csv(f'../../ddf--datapoints--{concept}--by--{by}.csv', index=False)


def serve_entities(entities):
    for e, d in entities.items():
        d_ = sort_df(d.drop_duplicates(), e)
        d_.to_csv(f'../../ddf--entities--{e}.csv', index=False)


def create_measure_concepts():
    j = get_all_series()
    cdf = pd.DataFrame.from_records(j)
    cdf['concept'] = cdf['code'].map(to_concept_id)
    cdf['concept_type'] = 'measure'
    cdf = cdf.rename(columns={'code': 'name'})
    cdf = cdf[['concept', 'name', 'concept_type', 'description', 'target', 'goal', 'indicator']]
    # cleanup some columns
    # these columns are list from the api data, change them to string
    for c in ['goal', 'indicator', 'target']:
        cdf[c] = cdf[c].map(lambda x: ', '.join(x))
    # description column have some unintented line breaks
    cdf['description'] = cdf['description'].map(lambda x: x.replace('\r', ''))

    return cdf


def create_geo_entity():
    geo_url = api_path(API_BASE, '/SDGAPI', '/v1/sdg/GeoArea/List')
    geo = req.get(geo_url)
    gdf = pd.DataFrame(geo.json())
    gdf.columns = ['geo_area', 'name']
    return gdf


def main():
    entities = {}

    for f in os.listdir('../source'):
        if not f.endswith('.csv'):
            continue

        name = f[:-4]
        concept = name.lower()
        print(concept)

        df = read_source(name)
        if df is None:
            print("\tno data")
            continue
        key_columns = get_key_columns(df)
        df = check_source(df, key_columns)

        # rename column names to their ddf concept id
        column_map = {'TimePeriod': 'year', 'GeoAreaCode': 'geo_area'}
        for c in key_columns[2:]:
            column_map[c] = to_concept_id(c)
        column_map['Value'] = concept

        df_ = df[[*key_columns, 'Value']].copy()
        df_.columns = [column_map[c] for c in df_.columns]

        # entities
        if len(key_columns) > 2:
            for c in df_.columns[2:-1]:
                if c in entities:
                    entities[c] = entities[c].append(create_entity(c, df_[c].unique()))
                else:
                    entities[c] = create_entity(c, df_[c].unique())
                # convert key columns into concept IDs
                df_[c] = df_[c].map(to_concept_id)
        serve_datapoints(df_, concept)

    # entities
    serve_entities(entities)

    # geo entity, from the api
    gdf = create_geo_entity()
    gdf = sort_df(gdf, 'geo_area')
    gdf.to_csv('../../ddf--entities--geo_area.csv', index=False)

    # concepts
    cdf = create_measure_concepts()
    cdf = sort_df(cdf, 'concept')
    cdf.to_csv('../../ddf--concepts--continuous.csv', index=False)

    cdf2 = pd.DataFrame({'concept': list(entities.keys())})
    cdf2['concept_type'] = 'entity_domain'
    cdf2['name'] = cdf2['concept'].map(lambda x: x.replace('_', ' ').title())

    cdf3 = pd.DataFrame({
        'concept': ['geo_area', 'year', 'name', 'description', 'goal', 'indicator', 'target'],
        'concept_type': ['entity_domain', 'time', 'string', 'string', 'string', 'string', 'string'],
        'name': ['Geo Area', 'Year', 'Name', 'Description', 'Goal', 'Indicator', 'Target']
    })
    cdf_ = cdf2.append(cdf3, ignore_index=True)
    cdf_ = sort_df(cdf_, 'concept')
    cdf_.to_csv('../../ddf--concepts--discrete.csv', index=False)


if __name__ == '__main__':
    main()
    print('Done.')
