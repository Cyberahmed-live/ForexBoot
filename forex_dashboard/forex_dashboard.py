from flask import Flask, send_file # type: ignore
import os

app = Flask(__name__)

@app.route("/forex_logs/trades_log.csv")
def get_log():
    file_path = os.path.join(os.path.dirname(__file__), "forex_logs/trades_log.csv")
    if os.path.exists(file_path):
        return send_file(file_path, mimetype="text/csv")
    return "Plik logu nie istnieje", 404

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
