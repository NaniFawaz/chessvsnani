from flask import Flask, render_template, request, jsonify
import os, shutil
import chess
from stockfish import Stockfish

app = Flask(__name__)

# --- Stockfish path: prefer env var, then system PATH, then common linux path ---
STOCKFISH_PATH = (
    os.environ.get("STOCKFISH_PATH")
    or shutil.which("stockfish")
    or "/usr/games/stockfish"
)

# --- Engine & board ---
board = chess.Board()
engine = Stockfish(path=STOCKFISH_PATH)

def configure_engine(state: str):
    """
    Tune engine strength & speed based on 'state':
      - sleeping: very weak + super fast
      - blindfold: medium + fast
      - nani: strong + still fast for web (200ms)
    """
    s = (state or "").strip().lower()
    if s == "sleeping":
        engine.set_skill_level(1)
        try: engine.set_elo_rating(400)
        except Exception: pass
        return 120  # ms think time
    elif s == "blindfold":
        engine.set_skill_level(8)
        try: engine.set_elo_rating(1400)
        except Exception: pass
        return 180
    else:  # "nani"
        engine.set_skill_level(18)
        try: engine.set_elo_rating(2200)
        except Exception: pass
        return 220

current_state = "sleeping"
move_time_ms = configure_engine(current_state)
engine.set_fen_position(board.fen())

# --- Routes ---
@app.get("/")
def index():
    return render_template("index.html")

@app.get("/get_fen")
def get_fen():
    return jsonify({"fen": board.fen()})

@app.post("/restart")
def restart():
    global board
    board = chess.Board()
    engine.set_fen_position(board.fen())
    return jsonify({"ok": True, "fen": board.fen()})

@app.post("/set_difficulty")
def set_difficulty():
    global current_state, move_time_ms, board
    data = request.get_json(silent=True) or {}
    state = (data.get("state") or "").strip().lower()
    if state not in {"sleeping", "blindfold", "nani"}:
        return jsonify({"error": "Invalid state. Use sleeping, blindfold, or nani."}), 400
    current_state = state
    move_time_ms = configure_engine(current_state)
    board = chess.Board()  # reset game on switch
    engine.set_fen_position(board.fen())
    return jsonify({"ok": True, "fen": board.fen(), "state": current_state})

@app.post("/move")
def make_move():
    """
    Body: { from: "e2", to: "e4" }  (also accept {source,target})
    Returns: { fen: "<new fen>" }  or { error: "..." }
    """
    data = request.get_json(silent=True) or {}
    src = (data.get("from") or data.get("source") or "").strip()
    dst = (data.get("to")   or data.get("target") or "").strip()
    if len(src) != 2 or len(dst) != 2:
        return jsonify({"error": "Bad move"}), 400

    # Try player's move
    try:
        move = board.parse_uci(src + dst)
    except Exception:
        return jsonify({"error": "Bad move"}), 400

    if move not in board.legal_moves:
        return jsonify({"error": "Illegal move"}), 400

    board.push(move)

    # Engine reply
    engine.set_fen_position(board.fen())
    try:
        # fast, predictable response for the web
        reply = engine.get_best_move_time(move_time_ms)
    except Exception:
        reply = None

    if reply:
        try:
            board.push_uci(reply)
        except Exception:
            # If wrapper gave a weird move, just keep player's move
            pass

    return jsonify({"fen": board.fen()})

# Render / gunicorn entrypoint
if __name__ == "__main__":
    # local dev
    app.run(host="0.0.0.0", port=5000, debug=True)
