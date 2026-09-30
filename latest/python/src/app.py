from flask import Flask, Response, request
from dotenv import dotenv_values
from datetime import date
import json
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


def run_script(script, *args):
    result = subprocess.run(
        ['python3', f'/app/src/{script}', *args],
        capture_output=True,
        text=True
    )
    logger.debug(result.stdout)
    logger.debug(result.stderr)
    return result

@app.route('/')

@app.route('/handle_request', methods=['GET'])

def handle_request():
    if request.args.get('token') == config['IBGATEWAY_TOKEN']:
        result = run_script('test_jobs.py')
        if result.returncode != 0:
            return Response(
                response=json.dumps({'error': f'{request.path} failed'}),
                status=500,
                mimetype='application/json'
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
        result = run_script('test_plot_clients.py')
        if result.returncode != 0:
            return Response(
                response=json.dumps({'error': f'{request.path} failed'}),
                status=500,
                mimetype='application/json'
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
        result = run_script('test_trades.py')
        if result.returncode != 0:
            return Response(
                response=json.dumps({'error': f'{request.path} failed'}),
                status=500,
                mimetype='application/json'
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
        result = run_script('test_compass.py')
        if result.returncode != 0:
            return Response(
                response=json.dumps({'error': f'{request.path} failed'}),
                status=500,
                mimetype='application/json'
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

    result = run_script(
        'cepea_differential.py',
        '--date', cepea_date.isoformat(),
        '--arabica', str(arabica),
        '--robusta', str(robusta)
    )
    if result.returncode != 0:
        return Response(
            response=json.dumps({'error': f'{request.path} failed'}),
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
