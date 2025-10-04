set -e

iris start IRIS quietly

iris session IRIS < /opt/irisapp/iris.script >> /opt/irisapp/logs/entrypoint.log 2>&1

iris stop IRIS quietly

exec /iris-main "$@"