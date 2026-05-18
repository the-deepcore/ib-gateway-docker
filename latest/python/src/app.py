from flask import Flask, Response, request
from dotenv import dotenv_values
import os
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

if __name__ == '__main__':
    app.run(host='0.0.0.0', port='5000', debug=True)
