from flask import Flask, render_template, request, jsonify
import chess
from stockfish import Stockfish

app = Flask(__name__)

# --- Engine & board setup ---
board = chess.Board()
# On your Mac, Homebrew path worked. On Render, we install system stockfish and call it from PATH:
stockfish = Stockfish(path="/usr/games/stockfish")


def set_nani(state: str):
    """Configure Stockfish strength based on Nani's state."""
    state = (state or "").lower().strip()
    stockfish.set_fen_position(board.fen())
    if state == "sleeping":
        stockfish.set_skill_level(1)
        try: stockfish.set_elo_rating(400)
        except Exception: pass
    elif state == "blindfold":
        stockfish.set_skill_level(8)
        try: stockfish.set_elo_rating(1200)
        except Exception: pass
    else:  # "nani" (max)
        stockfish.set_skill_level(20)
        try: stockfish.set_elo_rating(3500)
        except Exception: pass

current_state = "sleeping"
set_nani(current_state)

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/get_fen")
def get_fen():
    return jsonify({"fen": board.fen()})

@app.route("/set_difficulty", methods=["POST"])
def set_difficulty():
    global current_state, board
    data = request.get_json(silent=True) or {}
    state = (data.get("state") or "").lower().strip()
    if state not in {"sleeping", "blindfold", "nani"}:
        return jsonify({"error": "Invalid state"}), 400
    current_state = state
    board = chess.Board()  # reset game on switch
    set_nani(current_state)
    return jsonify({"ok": True, "state": current_state, "fen": board.fen()})

@app.route("/move", methods=["POST"])
def move():
    data = request.get_json(silent=True) or {}
    uci = (data.get("move") or "").strip()
    if len(uci) < 4:
        return jsonify({"error": "Bad move"}), 400

    # Human move
    try:
        human_move = chess.Move.from_uci(uci[:4])
    except Exception:
        return jsonify({"error": "Bad move format"}), 400
    if human_move not in board.legal_moves:
        return jsonify({"error": "Illegal move"}), 400

    board.push(human_move)

    # Engine reply (if game not over)
    if not board.is_game_over():
        stockfish.set_fen_position(board.fen())
        best = stockfish.get_best_move()
        if best:
            try:
                engine_move = chess.Move.from_uci(best)
                if engine_move in board.legal_moves:
                    board.push(engine_move)
            except Exception:
                pass

    return jsonify({"fen": board.fen()})

if __name__ == "__main__":
    # Local run (Render will use gunicorn app:app so this block won't run there)
    app.run(host="0.0.0.0", port=5000, debug=True)
