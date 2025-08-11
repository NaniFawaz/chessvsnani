from flask import Flask, render_template, request, jsonify, Response
import os, shutil
import chess, chess.pgn
from stockfish import Stockfish

app = Flask(__name__)

# --- Stockfish path (env, PATH, or common linux path) ---
STOCKFISH_PATH = (
    os.environ.get("STOCKFISH_PATH")
    or shutil.which("stockfish")
    or "/usr/games/stockfish"
)

board = chess.Board()
engine = Stockfish(path=STOCKFISH_PATH)

current_state = "sleeping"
move_time_ms = 250  # default quick reply
uci_moves: list[str] = []          # full move list (UCI)
redo_pairs: list[tuple[str,str]] = []  # stack of (user,engine) for redo

def configure_engine(state: str):
    global move_time_ms
    s = (state or "").strip().lower()
    if s == "sleeping":
        try: engine.set_skill_level(1)
        except Exception: pass
        try: engine.set_elo_rating(400)
        except Exception: pass
        move_time_ms = 180
    elif s == "blindfold":
        try: engine.set_skill_level(8)
        except Exception: pass
        try: engine.set_elo_rating(1400)
        except Exception: pass
        move_time_ms = 220
    else:  # nani
        try: engine.set_skill_level(18)
        except Exception: pass
        move_time_ms = 280

def status_payload():
    chk = board.is_check()
    check_square = None
    if chk:
        ks = board.king(board.turn)
        if ks is not None:
            check_square = chess.square_name(ks)
    over = board.is_game_over(claim_draw=True)
    reason = None
    if over:
        outcome = board.outcome(claim_draw=True)
        if outcome:
            if outcome.winner is None:
                reason = "Draw"
            else:
                reason = "Checkmate"
        else:
            reason = "Game over"
    last_uci = uci_moves[-1] if uci_moves else None
    last_from = last_uci[:2] if last_uci else None
    last_to = last_uci[2:4] if last_uci else None
    return {
        "fen": board.fen(),
        "in_check": chk,
        "check_square": check_square,
        "game_over": over,
        "game_over_reason": reason,
        "last_move": {"from": last_from, "to": last_to, "uci": last_uci} if last_uci else None
    }

@app.get("/")
def index():
    return render_template("index.html")

@app.get("/get_fen")
def get_fen():
    return jsonify(status_payload())

@app.post("/restart")
def restart():
    global board, uci_moves, redo_pairs
    board = chess.Board()
    uci_moves = []
    redo_pairs = []
    engine.set_fen_position(board.fen())
    return jsonify(status_payload())

@app.post("/set_difficulty")
def set_difficulty():
    global current_state, board, uci_moves, redo_pairs
    data = request.get_json(silent=True) or {}
    state = (data.get("state") or "").strip().lower()
    if state not in {"sleeping", "blindfold", "nani"}:
        return jsonify({"error": "Invalid state"}), 400
    current_state = state
    configure_engine(current_state)
    board = chess.Board()
    uci_moves = []
    redo_pairs = []
    engine.set_fen_position(board.fen())
    p = status_payload(); p["state"] = current_state
    return jsonify(p)

@app.post("/move")
def make_move():
    global uci_moves, redo_pairs
    data = request.get_json(silent=True) or {}
    src = (data.get("from") or data.get("source") or "").strip().lower()
    dst = (data.get("to")   or data.get("target") or "").strip().lower()
    if len(src) != 2 or len(dst) != 2:
        return jsonify({"error":"Bad move"}), 400
    try:
        mv = chess.Move.from_uci(src+dst)
    except Exception:
        return jsonify({"error":"Bad move"}), 400
    if mv not in board.legal_moves:
        # try auto-queen
        try:
            mv = chess.Move.from_uci(src+dst+'q')
        except Exception:
            pass
    if mv not in board.legal_moves:
        return jsonify({"error":"Illegal move"}), 400

    # new branch => clear redo
    redo_pairs.clear()

    # player's move
    uci_user = mv.uci()
    board.push(mv)
    uci_moves.append(uci_user)

    # engine reply (fast)
    engine.set_fen_position(board.fen())
    reply = None
    try:
        reply = engine.get_best_move_time(move_time_ms)
    except Exception:
        reply = None
    if reply:
        try:
            board.push_uci(reply)
            uci_moves.append(reply)
            # store pair for potential undo/redo
            redo_pairs.clear()
        except Exception:
            pass

    return jsonify(status_payload())

@app.post("/undo")
def undo():
    """Undo one full turn (user+engine) if possible."""
    global uci_moves, redo_pairs
    if len(uci_moves) >= 2:
        # pop engine then user; push pair to redo stack (user, engine)
        last_engine = uci_moves.pop()
        last_user = uci_moves.pop()
        redo_pairs.append((last_user, last_engine))
        # rebuild board from start
        tmp = chess.Board()
        for u in uci_moves:
            try: tmp.push_uci(u)
            except Exception: pass
        set_board(tmp)
    return jsonify(status_payload())

@app.post("/redo")
def redo():
    global uci_moves, redo_pairs
    if redo_pairs:
        user, eng = redo_pairs.pop()
        try:
            board.push_uci(user); uci_moves.append(user)
        except Exception: pass
        try:
            board.push_uci(eng); uci_moves.append(eng)
        except Exception: pass
    return jsonify(status_payload())

@app.get("/history")
def history():
    # build FENs by replaying uci_moves from start
    tmp = chess.Board()
    fens = [tmp.fen()]
    for u in uci_moves:
        try:
            tmp.push_uci(u)
            fens.append(tmp.fen())
        except Exception:
            break
    # also provide SAN list
    tmp2 = chess.Board()
    sans = []
    for u in uci_moves:
        mv = chess.Move.from_uci(u)
        sans.append(tmp2.san(mv))
        tmp2.push(mv)
    return jsonify({"fens": fens, "moves": sans, "uci": uci_moves})

@app.get("/pgn")
def pgn():
    game = chess.pgn.Game()
    node = game
    tmp = chess.Board()
    for u in uci_moves:
        mv = chess.Move.from_uci(u)
        node = node.add_variation(mv)
        tmp.push(mv)
    game.headers["Event"] = "Chess vs Nani"
    game.headers["Site"]  = "Online"
    game.headers["Result"] = tmp.result(claim_draw=True)
    return Response(str(game), mimetype="text/plain")

def set_board(new_board: chess.Board):
    global board
    board = new_board
    engine.set_fen_position(board.fen())

if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=True)
