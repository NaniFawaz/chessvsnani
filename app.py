from flask import Flask, render_template, request, jsonify
import os
import chess
from stockfish import Stockfish

app = Flask(__name__)

# --------- Engine & board ----------
board = chess.Board()

# On Render Docker we install stockfish; local dev can override via env
STOCKFISH_PATH = os.getenv("STOCKFISH_PATH", "/usr/games/stockfish")
engine = Stockfish(
    path=STOCKFISH_PATH,
    parameters={
        "Threads": 1,
        "Minimum Thinking Time": 50,  # stops long thinks
    },
)

def engine_reply(fen: str, move_time_ms: int = 150) -> str | None:
    """Get a quick reply move (UCI) from the engine for the given FEN."""
    try:
        engine.set_fen_position(fen)
        return engine.get_best_move_time(move_time_ms)
    except Exception:
        return None

# --------- Routes ----------
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
    return jsonify({"fen": board.fen()})

@app.post("/set_difficulty")
def set_difficulty():
    data = request.get_json(silent=True) or {}
    state = (data.get("state") or "").lower().strip()

    if state not in {"sleeping", "blindfold", "nani"}:
        return jsonify({"error": "Invalid state. Use sleeping, blindfold, or nani."}), 400

    # tune strength
    if state == "sleeping":
        engine.set_skill_level(0)
        engine.set_elo_rating(400)
        engine.set_depth(6)
    elif state == "blindfold":
        engine.set_skill_level(8)
        engine.set_elo_rating(1600)
        engine.set_depth(10)
    else:  # nani
        engine.set_skill_level(20)
        engine.set_depth(14)

    return jsonify({"ok": True, "fen": board.fen(), "state": state})

@app.post("/move")
def move():
    """Accepts JSON with keys 'from' and 'to' (or 'source'/'target')."""
    global board

    data = request.get_json(silent=True) or {}
    frm = (data.get("from") or data.get("source") or "").lower().strip()
    to  = (data.get("to")   or data.get("target") or "").lower().strip()

    # Validate shape quickly
    if len(frm) != 2 or len(to) != 2:
        return jsonify({"error": "Bad move"}), 400

    # Build UCI; auto-queen if a promotion is required
    uci = frm + to
    try:
        mv = chess.Move.from_uci(uci)
        if mv not in board.legal_moves:
            # try promotion-to-queen if needed
            try:
                mv = chess.Move.from_uci(uci + "q")
            except Exception:
                pass
        if mv not in board.legal_moves:
            return jsonify({"error": "Illegal move"}), 200
    except Exception:
        return jsonify({"error": "Bad move"}), 400

    # Apply user's move
    board.push(mv)

    # Engine reply (fast)
    reply = engine_reply(board.fen(), move_time_ms=150)
    if reply:
        try:
            emv = chess.Move.from_uci(reply)
            if emv in board.legal_moves:
                board.push(emv)
        except Exception:
            pass

    return jsonify({"fen": board.fen()})

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
