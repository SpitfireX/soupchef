# Soupchef

A Python script for scraping data from a big german recipe portal, chefkoch.de



## Installation

1. Make sure you're using **Python 3.6.4** and the latest **pipenv**. Installing pipenv is as easy as `pip install pipenv`
2. Install dependencies: `pipenv install`

That's it, your're set! Make sure everything's working by running `python soupchef.py --help`



## Usage

```
usage: soupchef.py [-h] (-d | -s | -u | -i) [-f] [-o OUTFOLDER] [-n NUM]
                   [-r RECURSION_DEPTH] [-c COMMENT_NUM] [-q] [-v] [-vv]
                   [input [input ...]]

Fetches recipes and their metadata from a big German cooking portal.

positional arguments:
  input               input arguments

optional arguments:
  -h, --help          show this help message and exit
  -d, --daily         Downloads the recipe of the day, no further input
                      required. Can be combined with -c and -r.
  -s, --search        Searches for the entered term and fetches the results.
                      Multiple searches need to be separated by spaces. Can be
                      combined with -n, -c and -r.
  -u, --url           Fetches the entered URLs. Can be combined with -c and
                      -r.
  -i, --id            Fetches the entered IDs. Can be combined with -c and -r.
  -f                  Force fetch all elements, don't skip already existing.
  -o OUTFOLDER        Sets the output folder.
  -n NUM              Sets the number of elements to fetch. For search
                      multiples of 30 are sensible values.
  -r RECURSION_DEPTH  Sets the number of recursion steps to take.
  -c COMMENT_NUM      Sets the number of comments to load per recipe.
  -q                  Suppress any console output
  -v                  Show all console output.
  -vv                 Show debug console output.```
