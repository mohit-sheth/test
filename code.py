#!/bin/python
# client id
# 325376081288-fb42dvlck5re4gid86o1c2d8vlaqel6p.apps.googleusercontent.com
# client secret
# QAsHkk__pBzpSKe4pLWJt0hL

import os
import gspread
from collections import defaultdict
from oauth2client.service_account import ServiceAccountCredentials
import csv
import sys
import re
import argparse
import datetime
from gspread_formatting import *

fmt = cellFormat(
    # backgroundColor=color(1, 0.9, 0.9),
    # textFormat=textFormat(bold=True, foregroundColor=color(1, 0, 1)),
    horizontalAlignment="RIGHT"
)


def parse_results(results_directory, result_dict):
    for root, dirs, files in os.walk("data/" + results_directory):
        dirs.sort(reverse=True)
        for file in files:
            if "rps" in file:
                key = "rps"
            if "latency" in file:
                key = "latency_95"
            file_to_open = f"{root}/{key}.txt"
            with open(file_to_open, "r") as f:
                val = f.read()
            iter_dict = result_dict
            for p in root.split(os.sep)[-4:]:                                       # start at processed-* in the dir
                iter_dict = iter_dict.setdefault(p, defaultdict(dict))              # 
            iter_dict.setdefault(results_directory, defaultdict(lambda: "NaN"))
            iter_dict[results_directory][key] = float(val.strip())


def generate_csv(file_name, results):
    with open("eggs.csv", "w", newline="") as csvfile:
        w = csv.writer(csvfile, delimiter=",", quotechar='"')
        create_structure(results, w)


def create_structure(results, w):
    test_types = [
        "processed-mix",
        "processed-reencrypt",
        "processed-passthrough",
        "processed-edge",
        "processed-http",
    ]
    level_header = {0: "Test Type", 1: "No. of routes", 2: "Conns/Route"}
    stack = [(k, 0, results[k]) for k in test_types if k in results]

    while stack:
        curr_node, depth, dictionary = stack.pop()
        w.writerow([" "] * depth + [level_header[depth]])
        w.writerow([" "] * depth + [regexp.match(curr_node).group(1) or curr_node])
        if "ka" not in list(dictionary.keys())[0]:
            stack_extension = [(k, depth + 1, dictionary[k]) for k in dictionary.keys()]
            stack.extend(stack_extension)
        else:
            print_tables(dictionary, depth + 1, w)


def print_tables(table_dictionary, offset, w):
    keepalive_counts = list(table_dictionary.keys())
    keepalive_counts.reverse()
    result_names = list(table_dictionary[keepalive_counts[0]].keys())
    result_types = list(table_dictionary[keepalive_counts[0]][result_names[0]].keys())
    row_offset = [" "] * (offset + 1)
    for result_type in reversed(result_types):
        if result_type == "latency_95":
            latency_flag = True
        else:
            latency_flag = False
        w.writerow(row_offset[1:] + [result_type])
        w.writerow(
            row_offset + ["Keepalive Count"] + result_names + [" "] + ["Percent Change", f"P/F (stdev={params.tolerance}%)"]
        )
        for keepalive_count in keepalive_counts:
            row = row_offset + [regexp.match(keepalive_count).group(1) or keepalive_count]
            for result_name in result_names:
                row.append(table_dictionary[keepalive_count][result_name][result_type])
            # Pass/Fail, only for last two columns of results
            row.append(" ")
            row.append("%.1f%%" % percent_change(float(row[-2]), float(row[-3])))
            row.append(
                get_pass_fail(
                    float(row[-3]), float(row[-4]), int(params.tolerance[0]), latency_flag,
                )
            )
            w.writerow(row)


def percent_change(value, reference):
    if reference:
        return ((value - reference) * 1.0 / reference) * 100
    else:
        return -1


def get_pass_fail(val, ref, tolerance, ltcy_flag):
    percent_diff = abs(percent_change(val, ref))
    if val < ref and percent_diff > tolerance:
        if ltcy_flag:
            return "Pass"
        else:
            return "Fail"
    elif val > ref and percent_diff > tolerance:
        if ltcy_flag:
            return "Fail"
        else:
            return "Pass"
    else:
        return "Pass"


now = datetime.datetime.today()
timestamp = now.strftime("%Y-%m-%d-%H.%M.%S")

parser = argparse.ArgumentParser()

parser.add_argument(
    "--tolerance",
    help="Accepted deviation (+/-) from the reference result",
    nargs=1,
    required=False,
    dest="tolerance",
    default="5",
)
parser.add_argument(
    "--sheetname",
    help="Google Spreadsheet name",
    nargs=1,
    required=False,
    dest="sheetname",
    default=f"router-test-results-{str(timestamp)}",
)
parser.add_argument(
    "--dirname",
    help="Google Spreadsheet name",
    nargs=1,
    required=False,
    dest="dir_name",
)

params = parser.parse_args()

regexp = re.compile(r"^([0-9]*)[a-z]*")

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive",
]
credentials = ServiceAccountCredentials.from_json_keyfile_name(
    "/home/msheth/graph_http/sheets-273020-b0f4e8a312c5.json", scope
)
gc = gspread.authorize(credentials)

results = defaultdict(dict)
result_dirs = ["OCP4.2", "OCP4.3"]  # Specify the directories
for result_dir in result_dirs:
    parse_results(result_dir, results)

sh = gc.create(params.sheetname)  # Specify name of the Spreadsheet
sh.share("msheth@redhat.com", perm_type="user", role="writer")
spreadsheet_id = sh.id
spreadsheet_url = "https://docs.google.com/spreadsheets/d/%s" % sh.id
print(f"\n Spreadsheet LINK is {spreadsheet_url}\n")
generate_csv("", results)

with open("eggs.csv", "r") as f:
    gc.import_csv(spreadsheet_id, f.read())
worksheet = sh.get_worksheet(0)
format_cell_range(worksheet, "1:1000", fmt)

