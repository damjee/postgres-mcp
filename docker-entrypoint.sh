#!/bin/sh
set -eu
# Never print or rewrite credentials. Forward arguments and signals unchanged.
exec "$@"
