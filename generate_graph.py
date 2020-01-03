'''
Generate a graph of geodata point count per partition region
to the total number of some measurement in the region.
'''

import logging
import argparse
import numpy as np
import pandas as pd
import scipy.optimize
from pathlib import Path
import matplotlib.pyplot as plt
from shapely.geometry import Point
from utils import init_logger, partition

logger = init_logger()
parser = argparse.ArgumentParser(description='Generate a graph of geodata point count per partition region to the total number of some measurement in the region.')
parser.add_argument('input', type=str, help='The path to the input geodata.')
parser.add_argument('y_columns', type=str, nargs='+', help='The (case-sensitive) header names of the variable columns.')
parser.add_argument('--longitude-col', dest='longitude_column', type=str, help='The (case-sensitive) header name of the longitude column.', default='LONGITUDE')
parser.add_argument('--latitude-col', dest='latitude_column', type=str, help='The (case-sensitive) header name of the latitude column.', default='LATITUDE')
parser.add_argument('-cw', '--chunk-width', type=int, help='The number of chunks on the longitude (horizontal). Defaults to 32.', default=32)
parser.add_argument('-ch', '--chunk-height', type=int, help='The number of chunks on the latitude (vertical). Defaults to 32.', default=32)
args = parser.parse_args()

input_path = Path(args.input)
if not (input_path.is_file() or input_path.exists()):
    logger.error('The specified input is not a file or does not exist!')
    exit(1)

def compute_weights(X, y, weight_func=None):
    '''
    Compute the weights from a set of data and a weight function.
    '''

    weights = None
    if weight_func is not None:
        weights = np.array([weight_func(X[i], y[i]) for i in range(len(X))])

    return weights

def coefficient_of_determination(X, y, trendline, weight_func=None):
    '''
    Calculate the coefficient of determination (R-squared value).
    '''

    if weight_func is not None:
        weights = compute_weights(X, y, weight_func)
    else:
        # All points are equally weighted
        weights = [1] * len(X)

    y_regression = trendline(X)  

    mean = np.average(y, weights=weights)

    # Calculate the total sum of squares (tss) and
    # the residual sum of squares.
    tss = np.sum(weights * (y - mean)**2)
    rss = np.sum(weights * (y_regression - y)**2)

    return 1 - rss / tss

def covariance(X, y, weights=None):
    '''
    Calculate the covariance.
    '''

    if weights is None:
        weights = [1] * len(X)
    
    return np.average((X - np.average(X, weights=weights)) * (y - np.average(y, weights=weights)), weights=weights)

def correlation_coefficient(X, y, weights=None):
    '''
    Calculates the Pearson correlation coefficient.
    '''

    if weights is None:
        weights = [1] * len(X)

    return covariance(X, y, weights) / np.sqrt(covariance(X, X, weights) * covariance(y, y, weights))

def _generate_trendline_metrics(X, y, trendline, weight_func=None):
    weights = compute_weights(X, y, weight_func)
    p_value = correlation_coefficient(X, y, weights)
    r_squared = coefficient_of_determination(X, y, trendline, weight_func)
    return p_value, r_squared

def generate_polynomial_trendline(X, y, weight_func=None, degree=1):
    '''
    Generate a polynomial fit trendline.
    '''

    weights = compute_weights(X, y, weight_func)
    trendline = np.poly1d(np.polyfit(X, y, degree, w=weights))
    p_value, r_squared = _generate_trendline_metrics(X, y, trendline, weight_func)
    return trendline, p_value, r_squared

def generate_curve_fit(X, y, f, weight_func=None):
    '''
    Generate a trendline for any function.
    '''

    weights = compute_weights(X, y, weight_func)
    popt, pcov = scipy.optimize.curve_fit(f, X, y, sigma=weights, absolute_sigma=weight_func is not None)
    trendline = lambda x: f(x, *popt)
    p_value, r_squared = _generate_trendline_metrics(X, y, trendline, weight_func)
    return trendline, p_value, r_squared

df = pd.read_csv(input_path)
points_geometry = [Point(xy) for xy in zip(df[args.longitude_column], df[args.latitude_column])]
chunks = partition(points_geometry, args.chunk_width, args.chunk_height)

X, Y = [], {y_column: list() for y_column in args.y_columns}
for i in range(args.chunk_width):
    for j in range(args.chunk_height):
        x = len(chunks[i][j])
        if x == 0: continue

        X.append(x)
        total_v = {y_column: 0 for y_column in args.y_columns}
        for point in chunks[i][j]:
            columns = df[(df[args.longitude_column] == point.x) & (df[args.latitude_column] == point.y)][args.y_columns]
            for column in columns:
                total_v[column] += sum(x if not np.isnan(x) else 0 for x in columns[column])
        
        for column in total_v:
            Y[column].append(total_v[column])

X = np.array(X)

# Sort the Xs so that matplotlib can properly display them.
sorted_X = np.array(sorted(X))
logger.setLevel(logging.INFO)

for column in Y:
    y = np.array(Y[column])
    plt.scatter(X, y)

    trendline, p, rsquared = generate_polynomial_trendline(X, y)
    plt.plot(sorted_X, trendline(sorted_X), linestyle='dashed', label='{} (linear)'.format(column))

    log_trendline, log_p, log_rsquared = generate_curve_fit(X, y, lambda t, a, b, c: a * np.log(b * t) + c)
    plt.plot(sorted_X, log_trendline(sorted_X), linestyle='dashed', label='{} (logarithmic)'.format(column))

    logger.info('{} - Correlation coefficient: {}'.format(column, round(p, 3)))
    logger.info('{} - R-squared (linear): {}'.format(column, round(rsquared, 3)))
    logger.info('{} - R-squared (logarithmic): {}'.format(column, round(log_rsquared, 3)))

plt.legend(loc='upper right')
plt.show()
