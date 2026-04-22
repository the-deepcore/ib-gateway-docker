from flask import Flask, Response

import os

app = Flask(__name__)

@app.route('/')

@app.route('/handle_post', methods=['POST'])

def handle_post():
    os.system("python3 /app/src/test_jobs.py 2>&1")
    return Response(
        response="{}",
        status=200,
        headers=[]
    )

if __name__ == '__main__':
  app.run(host='0.0.0.0',port='5000',debug=True)
