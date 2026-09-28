from flask import Flask, Response, request
from dotenv import dotenv_values
from datetime import date
import os
import subprocess
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

app = Flask(__name__)

logger = logging.getLogger(__name__)

config = dotenv_values("/tmp/secrets/.env")

@app.route('/')

@app.route('/handle_request', methods=['GET'])

def handle_request():
    if request.args.get('token') == config['IBGATEWAY_TOKEN']:
        logger.debug(
            os.system('python3 /app/src/test_jobs.py 2>&1')
        )
    else:
        logger.debug("Invalid token")

    return Response(
        response='{}',
        status=200,
        headers=[]
    )

@app.route('/handle_request_client', methods=['GET'])

def handle_request_client():
    if request.args.get('token') == config['IBGATEWAY_TOKEN']:
        logger.debug(
            os.system('python3 /app/src/test_plot_clients.py 2>&1')
        )
    else:
        logger.debug("Invalid token")

    return Response(
        response='{}',
        status=200,
        headers=[]
    )

@app.route('/handle_trades', methods=['GET'])

def handle_trades():
    if request.args.get('token') == config['IBGATEWAY_TOKEN']:
        logger.debug(
            os.system('python3 /app/src/test_trades.py 2>&1')
        )
    else:
        logger.debug("Invalid token")

    return Response(
        response='{}',
        status=200,
        headers=[]
    )

@app.route('/handle_compass', methods=['GET'])

def handle_compass():
    if request.args.get('token') == config['IBGATEWAY_TOKEN']:
        logger.debug(
            os.system('python3 /app/src/test_compass.py 2>&1')
        )
    else:
        logger.debug("Invalid token")

    return Response(
        response='{}',
        status=200,
        headers=[]
    )

@app.route('/cepea_differential', methods=['GET'])

def handle_cepea_differential():
    if request.args.get('token') != config['IBGATEWAY_TOKEN']:
        logger.debug("Invalid token")
        return Response(response='{}', status=200, headers=[])

    try:
        cepea_date = date.fromisoformat(request.args.get('date', ''))
        arabica = float(request.args['arabica'])
        robusta = float(request.args['robusta'])
    except (KeyError, ValueError):
        return Response(
            response='{"error": "expected date=YYYY-MM-DD, arabica=<float>, robusta=<float>"}',
            status=400,
            mimetype='application/json'
        )

    result = subprocess.run(
        ['python3', '/app/src/cepea_differential.py',
         '--date', cepea_date.isoformat(),
         '--arabica', str(arabica),
         '--robusta', str(robusta)],
        capture_output=True,
        text=True
    )
    logger.debug(result.stderr)
    if result.returncode != 0:
        return Response(
            response='{"error": "cepea_differential failed"}',
            status=500,
            mimetype='application/json'
        )

    # Last stdout line is the JSON result; ib_insync may log before it
    return Response(
        response=result.stdout.strip().splitlines()[-1],
        status=200,
        mimetype='application/json'
    )


if __name__ == '__main__':
    app.run(host='0.0.0.0', port='5000', debug=True)
