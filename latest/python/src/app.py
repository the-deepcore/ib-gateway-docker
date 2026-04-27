from flask import Flask, Response
import os
import logging

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

app = Flask(__name__)

logger = logging.getLogger(__name__)

@app.route('/')

@app.route('/handle_post', methods=['POST'])

def handle_post():
    logger.debug(
        os.system("python3 /app/src/test_jobs.py 2>&1")
    )
    return Response(
        response="{}",
        status=200,
        headers=[]
    )

if __name__ == '__main__':
    app.run(host='0.0.0.0',port='5000',debug=True)
