#!/usr/bin/env python3
# Gomoku.py
# Complete single-file Gomoku with GUI + AI (minimax/alpha-beta), timer, debug, and bonus rule options.
# Requires pygame: pip install pygame

import pygame
import sys
import time
import random
import threading
from collections import deque, namedtuple

# -----------------------
# Configuration / Globals
# -----------------------
BOARD_SIZE = 19       # required Goban size
CELL = 36             # pixels per cell (visual)
MARGIN = 40           # margin around board
SCREEN_W = max(MARGIN*2 + CELL*BOARD_SIZE, 1040)
FOOTER_HEIGHT = 190
SCREEN_H = MARGIN*2 + CELL*BOARD_SIZE + FOOTER_HEIGHT
FPS = 30

EMPTY = 0
BLACK = 1  # Player 1
WHITE = 2  # Player 2 / AI

INF = 10**9

# Heuristic pattern weights (tune these if you want stronger/weaker AI)
PATTERN_WEIGHTS = {
    "five": 100000000,
    "open_four": 1000000,
    "four": 50000,
    "open_three": 10000,
    "three": 1000,
    "open_two": 500,
    "two": 50,
}

# radius to generate candidate moves around existing stones
CANDIDATE_RADIUS = 2
ROOT_MOVE_LIMIT = 10
SEARCH_MOVE_LIMIT = 7
AI_TIME_LIMIT = 2.0
MIN_SEARCH_DEPTH = 1
MAX_SEARCH_DEPTH = 10

# colors
BG_COLOR = (230, 222, 210)
BOARD_COLOR = (210, 183, 140)
LINE_COLOR = (50, 50, 50)
BLACK_COLOR = (25, 25, 25)
WHITE_COLOR = (245, 245, 245)
HIGHLIGHT_COLOR = (218, 68, 83)
UI_BG = (35, 35, 40)
BUTTON_BG = (60, 60, 70)
BUTTON_HOVER = (78, 84, 96)
BUTTON_ACTIVE = (61, 112, 91)
BUTTON_BORDER = (105, 112, 125)
TEXT_COLOR = (252, 252, 252)
SUBTEXT_COLOR = (210, 210, 210)
OVERLAY_COLOR = (0, 0, 0, 100)
AI_MOVE_EVENT = pygame.USEREVENT + 1

# -----------------------
# Utilities
# -----------------------
def now():
    return time.perf_counter()

# -----------------------
# Board representation
# -----------------------
class Board:
    def __init__(self, size=BOARD_SIZE):
        self.size = size
        self.cells = [EMPTY] * (size*size)
        self.moves = []  # stack of moves (pos)
        self.last_move = -1
        self.captured_pairs = {BLACK: 0, WHITE: 0}
        self.history = []

    def copy(self):
        b = Board(self.size)
        b.cells = self.cells.copy()
        b.moves = self.moves.copy()
        b.last_move = self.last_move
        b.captured_pairs = self.captured_pairs.copy()
        b.history = self.history.copy()
        return b

    def index(self, r, c):
        return r * self.size + c

    def rc(self, idx):
        return idx // self.size, idx % self.size

    def get(self, r, c):
        if r<0 or c<0 or r>=self.size or c>=self.size: return None
        return self.cells[self.index(r,c)]

    def get_idx(self, idx):
        return self.cells[idx]

    def set_idx(self, idx, val):
        self.cells[idx] = val
        self.last_move = idx

    def _captured_by(self, idx, color):
        r, c = self.rc(idx)
        captured = set()
        for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (1, 1), (1, -1), (-1, 1), (-1, -1)):
            points = [(r + step * dr, c + step * dc) for step in (1, 2, 3)]
            if all(self.in_bounds(rr, cc) for rr, cc in points):
                a, b, end = (self.get(rr, cc) for rr, cc in points)
                if a == b == 3 - color and end == color:
                    captured.update(self.index(rr, cc) for rr, cc in points[:2])
        return captured

    def play(self, idx, color, check_forbidden=True):
        if idx < 0 or idx >= len(self.cells) or color not in (BLACK, WHITE) or self.cells[idx] != EMPTY:
            return False
        self.cells[idx] = color
        removed = self._captured_by(idx, color)
        for captured_idx in removed:
            self.cells[captured_idx] = EMPTY
        if check_forbidden and not removed and free_three_count(self, idx, color) >= 2:
            self.cells[idx] = EMPTY
            for captured_idx in removed:
                self.cells[captured_idx] = 3 - color
            return False
        previous_pairs = self.captured_pairs[color]
        self.captured_pairs[color] += len(removed) // 2
        self.moves.append(idx)
        self.history.append((idx, color, tuple(removed), previous_pairs))
        self.last_move = idx
        return True

    def undo(self):
        if not self.moves:
            return None
        idx = self.moves.pop()
        _, color, removed, previous_pairs = self.history.pop()
        self.cells[idx] = EMPTY
        for captured_idx in removed:
            self.cells[captured_idx] = 3 - color
        self.captured_pairs[color] = previous_pairs
        self.last_move = self.moves[-1] if self.moves else -1
        return idx

    def occupied_positions(self):
        return [i for i,v in enumerate(self.cells) if v != EMPTY]

    def empty_positions(self):
        return [i for i,v in enumerate(self.cells) if v == EMPTY]

    def is_full(self):
        return all(v != EMPTY for v in self.cells)

    def in_bounds(self, r, c):
        return 0 <= r < self.size and 0 <= c < self.size

    def winner_at(self, idx):
        # check if there's a win at last move idx: returns color or None
        if idx < 0: return None
        color = self.cells[idx]
        if color == EMPTY: return None
        if self.captured_pairs[color] >= 5:
            return color
        r, c = self.rc(idx)
        dirs = [(1,0), (0,1), (1,1), (1,-1)]
        for dr,dc in dirs:
            count = 1
            rr,cc = r+dr, c+dc
            while self.in_bounds(rr,cc) and self.get(rr,cc) == color:
                count += 1; rr += dr; cc += dc
            rr,cc = r-dr, c-dc
            while self.in_bounds(rr,cc) and self.get(rr,cc) == color:
                count += 1; rr -= dr; cc -= dc
            if count >= 5 and not self._line_can_be_captured(r, c, dr, dc, color):
                return color
        return None

    def _line_can_be_captured(self, r, c, dr, dc, color):
        # The opponent may answer a five by capturing a pair from that line.
        opponent = 3 - color
        found_line = False
        every_line_breakable = True
        for offset in range(-4, 1):
            segment = [(r + (offset + n) * dr, c + (offset + n) * dc) for n in range(5)]
            if not all(self.in_bounds(rr, cc) for rr, cc in segment):
                continue
            if not all(self.get(rr, cc) == color for rr, cc in segment):
                continue
            found_line = True
            line_breakable = False
            for sr, sc in segment:
                for ar, ac in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
                    mr, mc = sr - ar, sc - ac
                    er, ec = sr + 2 * ar, sc + 2 * ac
                    pr, pc = sr - 2 * ar, sc - 2 * ac
                    if not (self.in_bounds(mr, mc) and self.in_bounds(er, ec) and self.in_bounds(pr, pc)):
                        continue
                    # Opponent plays at one end of a pair of line stones and
                    # already has a stone immediately beyond the other end.
                    for move_r, move_c, a_r, a_c, b_r, b_c, end_r, end_c in (
                        (mr, mc, sr, sc, sr + ar, sc + ac, er, ec),
                        (er, ec, sr, sc, sr + ar, sc + ac, mr, mc),
                    ):
                        if self.get(move_r, move_c) != EMPTY or self.get(a_r, a_c) != color or self.get(b_r, b_c) != color or self.get(end_r, end_c) != opponent:
                            continue
                        self.cells[move_r * self.size + move_c] = opponent
                        self.cells[a_r * self.size + a_c] = EMPTY
                        self.cells[b_r * self.size + b_c] = EMPTY
                        still_five = False
                        for rr, cc in segment:
                            if self.get(rr, cc) == color:
                                i = self.index(rr, cc)
                                if self.winner_at_without_capture(i, color):
                                    still_five = True
                                    break
                        self.cells[move_r * self.size + move_c] = EMPTY
                        self.cells[a_r * self.size + a_c] = color
                        self.cells[b_r * self.size + b_c] = color
                        if not still_five:
                            line_breakable = True
                            break
                if line_breakable:
                    break
            if not line_breakable:
                every_line_breakable = False
        return found_line and every_line_breakable

    def winner_at_without_capture(self, idx, color):
        r, c = self.rc(idx)
        for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
            count = 1
            for sign in (-1, 1):
                rr, cc = r + sign * dr, c + sign * dc
                while self.in_bounds(rr, cc) and self.get(rr, cc) == color:
                    count += 1
                    rr += sign * dr
                    cc += sign * dc
            if count >= 5:
                return True
        return False

    def check_win(self):
        return self.winner_at(self.last_move)

    def winning_line_at(self, idx):
        """Return five coordinates witnessing a line win at idx, if present."""
        if idx < 0 or self.cells[idx] == EMPTY:
            return []
        color = self.cells[idx]
        r, c = self.rc(idx)
        for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
            points = [(r, c)]
            for sign in (-1, 1):
                rr, cc = r + sign * dr, c + sign * dc
                while self.in_bounds(rr, cc) and self.get(rr, cc) == color:
                    points.append((rr, cc))
                    rr += sign * dr
                    cc += sign * dc
            if len(points) >= 5 and not self._line_can_be_captured(r, c, dr, dc, color):
                points.sort(key=lambda point: point[0] * dr + point[1] * dc)
                anchor = points.index((r, c))
                start = max(0, min(anchor - 4, len(points) - 5))
                return points[start:start + 5]
        return []

# -----------------------
# Zobrist hashing for TT
# -----------------------
class Zobrist:
    def __init__(self, size):
        self.size = size
        rng = random.Random(1234567)
        self.table = [[rng.getrandbits(64) for _ in range(3)] for __ in range(size*size)]
        self.side = rng.getrandbits(64)

    def hash_board(self, board, side_to_move):
        h = 0
        for i, v in enumerate(board.cells):
            if v != EMPTY:
                h ^= self.table[i][v]
        if side_to_move == WHITE:
            h ^= self.side
        h ^= board.captured_pairs[BLACK] * 0x9E3779B185EBCA87
        h ^= board.captured_pairs[WHITE] * 0xC2B2AE3D27D4EB4F
        if board.last_move >= 0:
            h ^= (board.last_move + 1) * 0x165667B19E3779F9
        return h

# -----------------------
# Transposition Table
# -----------------------
Entry = namedtuple('Entry', 'depth score flag best')

class TranspositionTable:
    def __init__(self):
        self.table = {}

    def store(self, key, depth, score, flag, best):
        self.table[key] = Entry(depth, score, flag, best)

    def lookup(self, key):
        return self.table.get(key, None)

# -----------------------
# Move generation (candidates)
# -----------------------
def generate_candidates(board):
    # generate empty positions that are within radius of any occupied stone
    size = board.size
    occupied = board.occupied_positions()
    if not occupied:
        # first move: center
        return [board.index(size//2, size//2)]
    mark = [False] * (size*size)
    for idx in occupied:
        r,c = board.rc(idx)
        for dr in range(-CANDIDATE_RADIUS, CANDIDATE_RADIUS+1):
            for dc in range(-CANDIDATE_RADIUS, CANDIDATE_RADIUS+1):
                rr,cc = r+dr, c+dc
                if 0<=rr<size and 0<=cc<size:
                    i = board.index(rr,cc)
                    if board.cells[i] == EMPTY:
                        mark[i] = True
    cands = [i for i,flag in enumerate(mark) if flag]
    # if no neighbors found (rare), fallback to all empties
    if not cands:
        return board.empty_positions()
    return cands


def free_three_count(board, anchor, color):
    """Count directions where the move creates an extendable open four."""
    ar, ac = board.rc(anchor)
    count = 0
    for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
        creates_open_four = False
        for extension in range(-3, 4):
            if extension == 0:
                continue
            er, ec = ar + extension * dr, ac + extension * dc
            if not board.in_bounds(er, ec) or board.get(er, ec) != EMPTY:
                continue
            ext_idx = board.index(er, ec)
            board.cells[ext_idx] = color
            for start in range(-3, 1):
                cells = [(ar + (start + n) * dr, ac + (start + n) * dc) for n in range(4)]
                before = (ar + (start - 1) * dr, ac + (start - 1) * dc)
                after = (ar + (start + 4) * dr, ac + (start + 4) * dc)
                if not all(board.in_bounds(r, c) and board.get(r, c) == color for r, c in cells):
                    continue
                if not (board.in_bounds(*before) and board.get(*before) == EMPTY and
                        board.in_bounds(*after) and board.get(*after) == EMPTY):
                    continue
                if (ar, ac) in cells and (er, ec) in cells:
                    creates_open_four = True
                    break
            board.cells[ext_idx] = EMPTY
            if creates_open_four:
                break
        if creates_open_four:
            count += 1
    return count

# -----------------------
# Pattern-based heuristic
# -----------------------
# We'll scan lines in 4 directions and identify patterns like open_three, open_four, five, etc.
def evaluate(board, color):
    # return score from perspective of 'color'
    my = color
    opp = BLACK if color == WHITE else WHITE
    my_score = pattern_score(board, my)
    opp_score = pattern_score(board, opp)
    my_score += board.captured_pairs[my] * 1800
    opp_score += board.captured_pairs[opp] * 2200
    if board.captured_pairs[my] >= 4:
        my_score += 100000
    if board.captured_pairs[opp] >= 4:
        opp_score += 120000
    return my_score - opp_score

def pattern_score(board, player):
    size = board.size
    w = PATTERN_WEIGHTS
    score = 0
    # helper to evaluate a single line (list of values)
    def eval_line(line):
        nonlocal score
        L = len(line)
        i = 0
        while i < L:
            if line[i] != player:
                i += 1
                continue
            # found run of our stones starting at i
            j = i
            while j < L and line[j] == player:
                j += 1
            run_len = j - i
            left_empty = (i-1>=0 and line[i-1] == EMPTY)
            right_empty = (j < L and line[j] == EMPTY)
            if run_len >= 5:
                score += w["five"]
            elif run_len == 4:
                if left_empty and right_empty:
                    score += w["open_four"]
                else:
                    score += w["four"]
            elif run_len == 3:
                if left_empty and right_empty:
                    score += w["open_three"]
                elif left_empty or right_empty:
                    score += w["three"]
            elif run_len == 2:
                if left_empty and right_empty:
                    score += w["open_two"]
                else:
                    score += w["two"]
            else:
                score += 10  # single stone small
            i = j
    # scan rows
    for r in range(size):
        row = [board.get(r,c) for c in range(size)]
        eval_line(row)
    # scan cols
    for c in range(size):
        col = [board.get(r,c) for r in range(size)]
        eval_line(col)
    # diag TL-BR
    for k in range(-size+1, size):
        diag = []
        for r in range(size):
            c = r - k
            if 0 <= c < size:
                diag.append(board.get(r,c))
        if diag:
            eval_line(diag)
    # diag BL-TR
    for k in range(0, 2*size):
        diag = []
        for r in range(size):
            c = k - r
            if 0 <= c < size:
                diag.append(board.get(r,c))
        if diag:
            eval_line(diag)
    return score

# -----------------------
# Move ordering heuristics
# -----------------------
def move_heuristic(board, move, color):
    # simple local heuristic: how many friendly stones adjacent, and patterns created
    r,c = board.rc(move)
    score = 0
    for dr in (-1,0,1):
        for dc in (-1,0,1):
            if dr==0 and dc==0: continue
            rr,cc = r+dr, c+dc
            if 0<=rr<board.size and 0<=cc<board.size:
                v = board.get(rr,cc)
                if v == color:
                    score += 10
                elif v != EMPTY:
                    score += 12
    captured = len(board._captured_by(move, color))
    score += 500 * captured
    if board.captured_pairs[color] + captured // 2 >= 5:
        score += 100000000
    # bonus for centrality
    center = (board.size-1)/2
    dist = abs(r-center) + abs(c-center)
    score -= dist * 0.1
    return score


def root_tactical_bonus(board, move, color):
    """Promote immediate wins and blocks before the narrow root beam is cut."""
    r, c = board.rc(move)
    bonus = 0
    for dr, dc in ((1, 0), (0, 1), (1, 1), (1, -1)):
        own = other = 0
        for sign in (-1, 1):
            for player, name in ((color, "own"), (3 - color, "other")):
                step = 1
                count = 0
                while step <= 4:
                    rr, cc = r + sign * step * dr, c + sign * step * dc
                    if not board.in_bounds(rr, cc) or board.get(rr, cc) != player:
                        break
                    count += 1
                    step += 1
                if name == "own":
                    own += count
                else:
                    other += count
        if own >= 4:
            bonus += 100000000
        if other >= 4:
            bonus += 50000000
    return bonus


def immediate_winning_moves(board, color, candidates=None):
    """Return legal moves that win immediately for color."""
    moves = generate_candidates(board) if candidates is None else candidates
    wins = []
    for move in moves:
        if not board.play(move, color):
            continue
        if board.check_win() == color:
            wins.append(move)
        board.undo()
    return wins


def tactical_candidates(board, color, candidates):
    """Prioritize immediate wins and direct blocks before quiet moves."""
    wins = immediate_winning_moves(board, color, candidates)
    if wins:
        return wins
    threats = immediate_winning_moves(board, 3 - color, candidates)
    if threats:
        blocks = [move for move in threats if board.cells[move] == EMPTY]
        if blocks:
            return blocks
    return candidates

# -----------------------
# Negamax with alpha-beta, iterative deepening, TT, time control
# -----------------------
class AI:
    def __init__(self, color=WHITE, max_depth=10, time_limit=AI_TIME_LIMIT):
        self.color = color
        self.max_depth = max(MIN_SEARCH_DEPTH, min(MAX_SEARCH_DEPTH, int(max_depth)))
        self.time_limit = max(0.05, time_limit)
        self.zobrist = Zobrist(BOARD_SIZE)
        self.tt = TranspositionTable()
        self.nodes = 0
        self.start_time = 0
        self.end_time = 0
        self.best_move = None
        self.best_line = []
        self.stop = False
        self.pv = []
        self.completed_depth = 0
        self.root_bonus_cache = {}

    def reset_stats(self):
        self.nodes = 0
        self.best_move = None
        self.best_line = []
        self.pv = []
        self.completed_depth = 0
        self.root_bonus_cache = {}
        self.stop = False

    def time_up(self):
        return now() >= self.end_time

    def search(self, board, side_to_move, max_depth=None, time_limit=None):
        if max_depth is None: max_depth = self.max_depth
        max_depth = max(MIN_SEARCH_DEPTH, min(MAX_SEARCH_DEPTH, int(max_depth)))
        if time_limit is None: time_limit = self.time_limit
        time_limit = max(0.05, time_limit)
        self.reset_stats()
        self.start_time = now()
        self.end_time = self.start_time + time_limit
        best = -INF
        best_move = None
        self.pv = []
        # iterative deepening
        for depth in range(1, max_depth+1):
            if self.time_up(): break
            score, move, line = self.negamax_root(board, depth, side_to_move)
            if move is not None and best_move is None:
                # Keep a legal fallback even if the first iteration reaches
                # its time limit before the whole root pass finishes.
                best = score
                best_move = move
                self.pv = line
            if self.stop: break
            if move is not None:
                best = score
                best_move = move
                self.pv = line
                self.completed_depth = depth
            # small display update opportunity for UI; continue searching deeper
        self.best_move = best_move
        self.best_line = self.pv.copy()
        return best_move, best, self.pv

    def negamax_root(self, board, depth, color):
        alpha = -INF
        beta = INF
        best_score = -INF
        best_move = None
        best_line = []
        moves = generate_candidates(board)
        moves = tactical_candidates(board, color, moves)
        # order moves using simple heuristic and transposition table
        moves = self.order_moves_root(board, moves, color)[:ROOT_MOVE_LIMIT]
        for move_number, m in enumerate(moves):
            if self.time_up():
                self.stop = True
                break
            if not board.play(m, color):
                continue
            self.nodes += 1
            child_score, child_line = self.negamax(
                board, depth-1, -beta if move_number == 0 else -alpha-1,
                -alpha, 3-color)
            score = -child_score
            if move_number > 0 and score > alpha and not self.stop:
                child_score, child_line = self.negamax(board, depth-1, -beta, -alpha, 3-color)
                score = -child_score
            board.undo()
            if score > best_score:
                best_score = score
                best_move = m
                best_line = [m] + child_line
            alpha = max(alpha, score)
            if alpha >= beta:
                break
        return best_score, best_move, best_line

    def negamax(self, board, depth, alpha, beta, color):
        # timeout check
        if self.time_up():
            self.stop = True
            return 0, []
        alpha_orig = alpha
        # TT lookup
        key = self.zobrist.hash_board(board, color)
        entry = self.tt.lookup(key)
        if entry and entry.depth >= depth:
            if entry.flag == 'EXACT':
                return entry.score, []
            if entry.flag == 'LOWER' and entry.score > alpha:
                alpha = entry.score
            elif entry.flag == 'UPPER' and entry.score < beta:
                beta = entry.score
            if alpha >= beta:
                return entry.score, []

        win = board.check_win()
        if win == color:
            return INF - (self.max_depth - depth), []
        elif win == (3 - color):
            return -INF + (self.max_depth - depth), []
        if depth == 0:
            return evaluate(board, color), []

        self.nodes += 1
        moves = generate_candidates(board)
        moves = tactical_candidates(board, color, moves)
        # move ordering
        moves = self.order_moves(board, moves, color)[:SEARCH_MOVE_LIMIT]
        best_score = -INF
        best_move = None
        best_child_line = []

        for move_number, m in enumerate(moves):
            if not board.play(m, color):
                continue
            if move_number > 0 and depth >= 3:
                child_score, child_line = self.negamax(board, depth-2, -alpha-1, -alpha, 3-color)
                score = -child_score
                if score > alpha and not self.stop:
                    child_score, child_line = self.negamax(board, depth-1, -beta, -alpha, 3-color)
                    score = -child_score
            else:
                child_score, child_line = self.negamax(board, depth-1, -beta, -alpha, 3-color)
                score = -child_score
            board.undo()
            if self.stop:
                return 0, []
            if score > best_score:
                best_score = score
                best_move = m
                best_child_line = child_line
            alpha = max(alpha, score)
            if alpha >= beta:
                break

        # store in TT
        flag = 'EXACT'
        if best_score <= alpha_orig:
            flag = 'UPPER'
        elif best_score >= beta:
            flag = 'LOWER'
        self.tt.store(key, depth, best_score, flag, best_move)
        return best_score, ([best_move] + best_child_line if best_move is not None else [])

    def order_moves_root(self, board, moves, color):
        # try TT best first
        key = self.zobrist.hash_board(board, color)
        entry = self.tt.lookup(key)
        scored = []
        for m in moves:
            score = 0
            if entry and entry.best == m:
                score += 1000000
            cache_key = (key, color, m)
            if cache_key not in self.root_bonus_cache:
                self.root_bonus_cache[cache_key] = root_tactical_bonus(board, m, color)
            score += move_heuristic(board, m, color) + self.root_bonus_cache[cache_key]
            scored.append((score, m))
        scored.sort(reverse=True)
        return [m for s,m in scored]

    def order_moves(self, board, moves, color):
        entry = self.tt.lookup(self.zobrist.hash_board(board, color))
        scored = []
        for m in moves:
            score = move_heuristic(board, m, color)
            if entry and entry.best == m:
                score += 1000000
            scored.append((score, m))
        scored.sort(reverse=True)
        return [m for s,m in scored]

# -----------------------
# UI (pygame)
# -----------------------
class GUI:
    def __init__(self):
        pygame.init()
        self.size = BOARD_SIZE
        self.screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))
        pygame.display.set_caption("Gomoku - Python")
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont("Arial", 16)
        self.bigfont = pygame.font.SysFont("Arial", 20, bold=True)
        self.button_font = pygame.font.SysFont("Arial", 15, bold=True)
        self.review_font = pygame.font.SysFont("Arial", 11, bold=True)
        self.board = Board(self.size)
        self.current_turn = BLACK
        self.ai = AI(color=WHITE, max_depth=10, time_limit=AI_TIME_LIMIT)
        self.ai_enabled = True
        self.running = True
        self.debug = False
        self.last_ai_time = 0.0
        self.rules = ["Standard", "Pro", "Swap", "Swap2"]
        self.rule_index = 0
        self.selected_rule = self.rules[self.rule_index]
        self.rule_stage = None           # opening stage tracking for swap/swap2
        self.opening_queue = deque()     # forced colors to place before normal play
        self.swap_choice_pending = False # true when second player can decide to swap
        self.swap2_request_available = False
        self.button_rects = {}
        self.ai_thinking = False
        self.message = ""
        self.hotseat = False
        self.suggest_move = None
        self.ai_job_id = 0       # used to discard stale AI results
        self.game_over = False
        self.game_over_text = ""
        self.game_over_reason = ""
        self.winning_line = []
        self.winning_move = None
        self.winning_captures = []
        self.show_result_overlay = False
        self.review_mode = False
        self.result_button_rect = None

    def is_human_turn(self):
        # human can always act in hotseat, when AI is disabled, or when current turn differs from AI color
        if self.ai_thinking:
            return False
        if self.game_over:
            return False
        return self.hotseat or not self.ai_enabled or self.current_turn != self.ai.color

    def should_ai_move(self):
        if self.ai_thinking or not self.ai_enabled or self.hotseat:
            return False
        if self.opening_queue or self.swap_choice_pending:
            return False
        if self.board.check_win() or self.game_over:
            return False
        return self.current_turn == self.ai.color

    def cycle_rule(self, direction=1):
        self.rule_index = (self.rule_index + direction) % len(self.rules)
        self.selected_rule = self.rules[self.rule_index]
        self.reset_game()
        opening_note = f" {self.message}" if self.message else ""
        self.message = f"Rule set: {self.selected_rule}.{opening_note}"

    def swap_colors(self):
        # swap AI color vs human color and set turn to black (as per swap rules)
        new_color = BLACK if self.ai.color == WHITE else WHITE
        ai_depth = self.ai.max_depth
        ai_time = self.ai.time_limit
        self.ai = AI(color=new_color, max_depth=ai_depth, time_limit=ai_time)
        self.current_turn = BLACK
        self.swap_choice_pending = False
        self.swap2_request_available = False
        self.rule_stage = None
        self.opening_queue.clear()
        self.message = "Colors swapped. Black to move."

    def request_two_more(self):
        # swap2 option: first player must place two more stones (white then black)
        if self.selected_rule != "Swap2" or not self.swap2_request_available:
            return
        self.opening_queue = deque([WHITE, BLACK])
        self.swap_choice_pending = False
        self.swap2_request_available = False
        self.rule_stage = "swap2_extra"
        self.message = "Swap2: place extra White then Black stones."

    def handle_ai_swap_decision(self):
        # simple heuristic: AI swaps if the other color currently evaluates better
        if not self.swap_choice_pending or self.current_turn != self.ai.color:
            return
        cur_score = evaluate(self.board, self.ai.color)
        swap_score = evaluate(self.board, BLACK if self.ai.color == WHITE else WHITE)
        if swap_score > cur_score + 500:  # margin to avoid jitter
            self.swap_colors()
        else:
            # keep colors; allow normal move
            self.swap_choice_pending = False
            self.swap2_request_available = False
            self.rule_stage = None
            self.message = "Staying with current colors."

    def process_after_move(self, mover_color):
        winner = self.board.check_win()
        if winner:
            self.game_over = True
            self.show_result_overlay = True
            winner_name = 'Black' if winner == BLACK else 'White'
            if self.board.captured_pairs[winner] >= 5:
                pair_count = self.board.captured_pairs[winner]
                self.game_over_reason = f"Capture win: {winner_name} captured {pair_count} pairs (target: 5)."
                self.winning_line = []
                self.winning_captures = list(self.board.history[-1][2]) if self.board.history else []
            else:
                self.winning_line = self.board.winning_line_at(self.board.last_move)
                self.winning_captures = []
                if self.winning_line:
                    start = (self.winning_line[0][0] + 1, self.winning_line[0][1] + 1)
                    end = (self.winning_line[-1][0] + 1, self.winning_line[-1][1] + 1)
                    self.game_over_reason = f"Five in a row: from {start} to {end}."
                else:
                    self.game_over_reason = "A five-stone line cannot be broken by a capture."
            self.winning_move = self.board.last_move
            self.game_over_text = f"{winner_name} wins!"
            self.message = self.game_over_text
            self.ai_thinking = False
            return True
        if self.board.is_full():
            self.game_over = True
            self.show_result_overlay = True
            self.game_over_text = "Draw game."
            self.game_over_reason = "Every intersection is occupied and there is no winner."
            self.winning_line = []
            self.winning_move = None
            self.winning_captures = []
            self.message = self.game_over_text
            self.ai_thinking = False
            return True

        # swap rule: after very first move, white can choose to swap
        if self.selected_rule == "Swap" and len(self.board.moves) == 1:
            self.swap_choice_pending = True
            self.current_turn = WHITE
            self.message = "Swap: White may click 'Swap Colors' or just play."
            return False

        if self.swap_choice_pending:
            # accepting current colors by playing
            self.swap_choice_pending = False
            self.swap2_request_available = False
            self.rule_stage = None

        self.current_turn = BLACK if mover_color == WHITE else WHITE
        return False

    def reset_game(self):
        # invalidate any in-flight AI search
        self.ai_job_id += 1
        self.ai_thinking = False
        self.board = Board(self.size)
        self.current_turn = BLACK
        ai_color = self.ai.color if hasattr(self, "ai") and self.ai else WHITE
        ai_depth = self.ai.max_depth if hasattr(self, "ai") and self.ai else 10
        ai_time = self.ai.time_limit if hasattr(self, "ai") and self.ai else AI_TIME_LIMIT
        self.ai = AI(color=ai_color, max_depth=ai_depth, time_limit=ai_time)
        self.last_ai_time = 0.0
        self.suggest_move = None
        self.ai_thinking = False
        self.message = ""
        self.game_over = False
        self.game_over_text = ""
        self.game_over_reason = ""
        self.winning_line = []
        self.winning_move = None
        self.winning_captures = []
        self.show_result_overlay = False
        self.review_mode = False
        self.result_button_rect = None
        # handle special starting rules if chosen
        self.opening_queue.clear()
        self.swap_choice_pending = False
        self.swap2_request_available = False
        self.rule_stage = None
        if self.selected_rule == "Pro":
            # Pro: first move must be center by Black; start from there.
            center = self.board.index(self.size//2, self.size//2)
            self.board.play(center, BLACK)
            self.current_turn = WHITE
            self.message = "Pro opening: Black starts at center."
        elif self.selected_rule == "Swap":
            # Normal start; after the first move, White may swap colors.
            self.rule_stage = "swap_pending"
            self.message = "Swap opening: after first move, White may swap."
        elif self.selected_rule == "Swap2":
            # First player places Black, White, Black before White chooses.
            self.rule_stage = "swap2_first3"
            self.opening_queue = deque([BLACK, WHITE, BLACK])
            self.message = "Swap2: place B, W, B then choose to swap or ask two more."

    def pos_to_cell(self, pos):
        x,y = pos
        bx = (x - MARGIN) // CELL
        by = (y - MARGIN) // CELL
        if 0 <= bx < self.size and 0 <= by < self.size:
            return int(by), int(bx)
        return None

    def cell_to_pos(self, r,c):
        x = MARGIN + c*CELL + CELL//2
        y = MARGIN + r*CELL + CELL//2
        return x,y

    def handle_click(self, pos):
        if self.game_over:
            return
        cell = self.pos_to_cell(pos)
        if not cell:
            return
        r,c = cell
        idx = self.board.index(r,c)
        if self.board.get_idx(idx) != EMPTY:
            return

        # forced opening stones (swap2 opening handled here, always manual)
        if self.opening_queue:
            expected = self.opening_queue[0]
            played = self.board.play(idx, expected)
            if played:
                self.opening_queue.popleft()
                if not self.opening_queue:
                    if self.rule_stage == "swap2_first3":
                        self.swap_choice_pending = True
                        self.swap2_request_available = True
                        self.current_turn = WHITE
                        self.rule_stage = "swap2_choice"
                        self.message = "Swap2: White may swap, ask two more, or play."
                    elif self.rule_stage == "swap2_extra":
                        self.swap_choice_pending = True
                        self.current_turn = WHITE
                        self.rule_stage = "swap2_choice"
                        self.message = "Swap2: decide to swap or play."
                else:
                    # update turn indicator to next forced color
                    self.current_turn = self.opening_queue[0]
                return

        # if swap choice pending, playing equals accepting colors
        if self.swap_choice_pending:
            if not self.is_human_turn():
                return
            played = self.board.play(idx, self.current_turn)
            if not played:
                self.message = "Illegal move: double-three is forbidden."
                return
            if played:
                self.suggest_move = None
                finished = self.process_after_move(self.current_turn)
                if not finished and self.ai_enabled and not self.swap_choice_pending and not self.opening_queue and self.current_turn == self.ai.color:
                    self.run_ai_move()
            return

        # normal move path
        if not self.is_human_turn():
            return
        played = self.board.play(idx, self.current_turn)
        if not played:
            self.message = "Illegal move: double-three is forbidden."
            return
        if played:
            self.suggest_move = None
            finished = self.process_after_move(self.current_turn)
            if not finished and self.ai_enabled and not self.swap_choice_pending and not self.opening_queue and self.current_turn == self.ai.color:
                self.run_ai_move()

    def handle_button_click(self, pos):
        if self.result_button_rect and self.result_button_rect.collidepoint(pos):
            self.show_result_overlay = False
            self.review_mode = True
            return True
        for key, rect in self.button_rects.items():
            if rect.collidepoint(pos):
                if key == "new":
                    self.reset_game()
                elif key == "ai":
                    self.ai_enabled = not self.ai_enabled
                    if self.ai_enabled:
                        self.hotseat = False
                    else:
                        self.ai_job_id += 1
                        self.ai_thinking = False
                elif key == "hotseat":
                    self.hotseat = not self.hotseat
                    if self.hotseat:
                        self.ai_enabled = False
                        self.ai_job_id += 1
                        self.ai_thinking = False
                    else:
                        self.ai_enabled = True
                elif key == "suggest":
                    self.suggest()
                elif key == "result":
                    self.show_result_overlay = True
                    self.review_mode = False
                elif key == "debug":
                    self.debug = not self.debug
                elif key == "depth+":
                    self.ai.max_depth = min(MAX_SEARCH_DEPTH, self.ai.max_depth + 1)
                elif key == "depth-":
                    self.ai.max_depth = max(MIN_SEARCH_DEPTH, self.ai.max_depth - 1)
                elif key == "swap":
                    if self.swap_choice_pending:
                        self.swap_colors()
                elif key == "ask2":
                    self.request_two_more()
                elif key == "rule+":
                    self.cycle_rule(1)
                elif key == "rule-":
                    self.cycle_rule(-1)
                return True
        return False

    def run_ai_move(self):
        # run AI search asynchronously to keep UI responsive
        if self.ai_thinking or self.game_over or self.swap_choice_pending or self.opening_queue or self.board.check_win():
            return
        self.ai_thinking = True
        self.last_ai_time = 0.0
        self.message = "AI thinking..."
        self.ai_job_id += 1
        job_id = self.ai_job_id
        snapshot = self.board.copy()
        color = self.current_turn
        ai_obj = self.ai
        threading.Thread(
            target=self._ai_worker,
            args=(ai_obj, snapshot, color, job_id),
            daemon=True,
        ).start()

    def _ai_worker(self, ai_obj, board_snapshot, color, job_id):
        t0 = now()
        move, score, pv = ai_obj.search(
            board_snapshot,
            color,
            max_depth=ai_obj.max_depth,
            time_limit=ai_obj.time_limit,
        )
        t1 = now()
        pygame.event.post(
            pygame.event.Event(
                AI_MOVE_EVENT,
                {
                    "job_id": job_id,
                    "move": move,
                    "score": score,
                    "pv": pv,
                    "duration": t1 - t0,
                    "nodes": ai_obj.nodes,
                    "color": color,
                },
            )
        )

    def handle_ai_result(self, event):
        # ignore stale AI results (e.g., after reset)
        if event.job_id != self.ai_job_id:
            return
        self.ai_thinking = False
        self.last_ai_time = event.duration
        self.ai.best_line = event.pv or []
        self.ai.nodes = event.nodes
        # A search result is only valid for the exact AI turn that started it.
        # In particular, never apply a stale result after a color/turn change.
        if event.color != self.ai.color or self.current_turn != self.ai.color:
            return
        if self.swap_choice_pending or self.opening_queue:
            return
        move = event.move
        if move is not None:
            if not (0 <= move < len(self.board.cells)) or self.board.get_idx(move) != EMPTY:
                self.message = "AI result rejected: intersection is no longer empty."
                return
            if not self.board.play(move, self.current_turn):
                self.message = "AI result rejected: move is not legal."
                return
            captured = self.board.history[-1][2]
            finished = self.process_after_move(self.current_turn)
            if not finished:
                details = ""
                if captured:
                    coordinates = ", ".join(str(self.board.rc(idx)) for idx in captured)
                    details = f"; captured pair at {coordinates} (subject capture rule)"
                self.message = f"AI move {self.board.rc(move)} score {event.score} time {self.last_ai_time:.2f}s nodes {event.nodes}{details}"
        else:
            self.message = "AI found no move (draw?)"

    def suggest(self):
        # run AI for shorter time/depth to suggest a move for human
        if self.game_over:
            self.message = "Suggestions are unavailable after the game ends."
            return
        if self.opening_queue or self.swap_choice_pending:
            self.message = "Suggestion unavailable during opening/swap decision."
            return
        if self.ai_thinking:
            self.message = "Wait for AI to finish thinking."
            return
        temp_ai = AI(color=self.current_turn, max_depth=self.ai.max_depth, time_limit=self.ai.time_limit)
        move, score, pv = temp_ai.search(self.board, self.current_turn, max_depth=temp_ai.max_depth, time_limit=temp_ai.time_limit)
        self.suggest_move = move
        if move is not None:
            self.message = f"Suggestion: play at {self.board.rc(move)} (score {score})"

    def draw_board(self):
        self.screen.fill(BG_COLOR)
        board_px = CELL * self.size
        pygame.draw.rect(self.screen, UI_BG, (MARGIN-6, MARGIN-6, board_px+12, board_px+12), border_radius=4)
        pygame.draw.rect(self.screen, BOARD_COLOR, (MARGIN, MARGIN, board_px, board_px))
        # Draw one line through the center of each playable intersection.
        grid_start = MARGIN + CELL // 2
        grid_end = MARGIN + board_px - CELL // 2
        for i in range(self.size):
            x = grid_start + i * CELL
            pygame.draw.line(self.screen, LINE_COLOR, (x, grid_start), (x, grid_end), 1)
            y = grid_start + i * CELL
            pygame.draw.line(self.screen, LINE_COLOR, (grid_start, y), (grid_end, y), 1)

        # Keep the opening screen balanced: the board has a dedicated rules
        # panel beside it, and the optional debug view can use the same space.
        side_x = MARGIN + board_px + 20
        side_rect = pygame.Rect(side_x, MARGIN, SCREEN_W - side_x - 20, board_px)
        pygame.draw.rect(self.screen, UI_BG, side_rect, border_radius=10)
        sidebar_lines = [
            ("GOMOKU", self.bigfont, TEXT_COLOR),
            ("Make five in a row to win.", self.font, TEXT_COLOR),
            ("Capture five pairs to win too.", self.font, TEXT_COLOR),
            ("", self.font, TEXT_COLOR),
            ("HOW TO PLAY", self.font, (255, 211, 64)),
            ("Click an intersection to place", self.font, SUBTEXT_COLOR),
            ("a stone. Black and White take turns." if self.hotseat or not self.ai_enabled
             else f"a stone. The AI plays {'Black' if self.ai.color == BLACK else 'White'}.",
             self.font, SUBTEXT_COLOR),
            ("", self.font, TEXT_COLOR),
            ("CONTROLS", self.font, (255, 211, 64)),
            ("N  New game", self.font, SUBTEXT_COLOR),
            ("S  Suggest a move", self.font, SUBTEXT_COLOR),
            ("D  Toggle debug", self.font, SUBTEXT_COLOR),
            ("R  Change opening rule", self.font, SUBTEXT_COLOR),
            ("V  Toggle result / board", self.font, SUBTEXT_COLOR),
        ]
        side_y = MARGIN + 20
        for label, font, color in sidebar_lines:
            if label:
                self.screen.blit(font.render(label, True, color), (side_x + 14, side_y))
            side_y += 28 if font == self.bigfont else 24

        # star points (like go) at cell centers
        stars = [3, self.size//2, self.size-4] if self.size>=11 else [self.size//2]
        for r in stars:
            for c in stars:
                px, py = self.cell_to_pos(r, c)
                pygame.draw.circle(self.screen, LINE_COLOR, (px, py), 4)

        # stones
        for idx, val in enumerate(self.board.cells):
            if val != EMPTY:
                r,c = self.board.rc(idx)
                x, y = self.cell_to_pos(r, c)
                pos = (x, y)
                color = BLACK_COLOR if val==BLACK else WHITE_COLOR
                pygame.draw.circle(self.screen, color, pos, CELL//2 - 4)
                pygame.draw.circle(self.screen, LINE_COLOR, pos, CELL//2 - 4, 1)

        # suggested highlight
        if self.suggest_move is not None:
            r,c = self.board.rc(self.suggest_move)
            x,y = self.cell_to_pos(r,c)
            pygame.draw.circle(self.screen, (0,200,0), (x,y), CELL//2 - 6, 3)

        # last move highlight
        if self.board.last_move >= 0:
            r,c = self.board.rc(self.board.last_move)
            x,y = self.cell_to_pos(r,c)
            pygame.draw.circle(self.screen, HIGHLIGHT_COLOR, (x,y), 6, 2)

        # Keep the finished position visible on demand. The result panel can be
        # dismissed without clearing the game, and the board remains locked.
        self.result_button_rect = None
        if self.game_over:
            if self.show_result_overlay:
                overlay = pygame.Surface((board_px, board_px), pygame.SRCALPHA)
                overlay.fill(OVERLAY_COLOR)
                self.screen.blit(overlay, (MARGIN, MARGIN))
            if self.winning_line:
                points = [self.cell_to_pos(r, c) for r, c in self.winning_line]
                pygame.draw.lines(self.screen, (32, 150, 76), False, points, 5)
                for point in points:
                    pygame.draw.circle(self.screen, (255, 211, 64), point, CELL // 2 - 2, 3)
            if self.review_mode and not self.show_result_overlay:
                move_order = {}
                for move_number, (move, _color, _removed, _previous_pairs) in enumerate(self.board.history, start=1):
                    move_order[move] = move_number
                for idx, val in enumerate(self.board.cells):
                    if val == EMPTY or idx not in move_order:
                        continue
                    x, y = self.cell_to_pos(*self.board.rc(idx))
                    label_color = WHITE_COLOR if val == BLACK else BLACK_COLOR
                    label = self.review_font.render(str(move_order[idx]), True, label_color)
                    self.screen.blit(label, label.get_rect(center=(x, y)))

                if self.winning_move is not None:
                    x, y = self.cell_to_pos(*self.board.rc(self.winning_move))
                    pygame.draw.circle(self.screen, (255, 211, 64), (x, y), CELL // 2 - 1, 3)
                for idx in self.winning_captures:
                    x, y = self.cell_to_pos(*self.board.rc(idx))
                    pygame.draw.circle(self.screen, (218, 68, 83), (x, y), CELL // 2 - 3, 2)
                    arm = 5
                    pygame.draw.line(self.screen, (218, 68, 83), (x - arm, y - arm), (x + arm, y + arm), 2)
                    pygame.draw.line(self.screen, (218, 68, 83), (x - arm, y + arm), (x + arm, y - arm), 2)
            if self.show_result_overlay:
                center_x = MARGIN + board_px // 2
                card = pygame.Rect(MARGIN + (board_px - 560) // 2,
                                   MARGIN + board_px // 2 - 92, 560, 184)
                pygame.draw.rect(self.screen, UI_BG, card, border_radius=12)
                pygame.draw.rect(self.screen, (255, 211, 64), card, 2, border_radius=12)
                title = self.bigfont.render(self.game_over_text, True, WHITE_COLOR)
                self.screen.blit(title, title.get_rect(center=(center_x, card.y + 34)))
                reason = self.font.render(self.game_over_reason, True, SUBTEXT_COLOR)
                self.screen.blit(reason, reason.get_rect(center=(center_x, card.y + 70)))
                hint = self.font.render("View the finished board or start a new game below.", True, SUBTEXT_COLOR)
                self.screen.blit(hint, hint.get_rect(center=(center_x, card.y + 98)))
                self.result_button_rect = pygame.Rect(center_x - 74, card.y + 122, 148, 38)
                self.draw_button("View Board", self.result_button_rect, active=True)

        # turn indicator
        ui_top = SCREEN_H - 180
        turn_text = "Game Over" if self.game_over else f"Turn: {'Black' if self.current_turn==BLACK else 'White'}"
        surf = self.bigfont.render(turn_text, True, TEXT_COLOR)
        turn_rect = pygame.Rect(MARGIN-6, ui_top + 6, 260, 28)
        pygame.draw.rect(self.screen, UI_BG, turn_rect, border_radius=6)
        self.screen.blit(surf, (turn_rect.x+10, turn_rect.y+4))

        # message + AI info panel
        msg_rect = pygame.Rect(MARGIN+270, ui_top + 6, SCREEN_W - (MARGIN+270) - MARGIN, 46)
        pygame.draw.rect(self.screen, UI_BG, msg_rect, border_radius=6)
        if self.review_mode and not self.show_result_overlay:
            if self.winning_move is not None:
                winning_color = self.board.get_idx(self.winning_move)
                winner_name = "Black" if winning_color == BLACK else "White"
                if self.winning_captures:
                    result_note = f"Review: {winner_name} won by capture; numbers show move order."
                else:
                    result_note = f"Review: {winner_name} won with five; numbers show move order."
                msg_lines = [result_note]
            else:
                msg_lines = ["Review: draw; numbers show move order."]
            if self.winning_captures:
                msg_lines.append("Gold marks the winning move; red Xs mark stones it captured.")
            elif self.winning_line:
                msg_lines.append("Green marks the winning line; gold marks its last move.")
        else:
            msg_lines = [self.message]
        if not (self.review_mode and not self.show_result_overlay) and self.ai_thinking:
            msg_lines.append(f"AI thinking... depth {self.ai.max_depth} | limit {self.ai.time_limit}s | nodes {self.ai.nodes}")
        elif not (self.review_mode and not self.show_result_overlay):
            msg_lines.append(f"AI last: {self.last_ai_time:.2f}s | nodes {self.ai.nodes}")
        y = msg_rect.y + 6
        for ln in msg_lines:
            line_surf = self.font.render(ln, True, TEXT_COLOR if ln == msg_lines[0] else SUBTEXT_COLOR)
            self.screen.blit(line_surf, (msg_rect.x+10, y))
            y += 18

        # rule/status line
        rule_line = f"Rule: {self.selected_rule}"
        rule_line += f" | Captures B {self.board.captured_pairs[BLACK]}/5  W {self.board.captured_pairs[WHITE]}/5"
        if self.opening_queue:
            rule_line += " | Opening placement"
        elif self.swap_choice_pending:
            rule_line += " | Swap decision pending"
        rule_rect = pygame.Rect(MARGIN-6, SCREEN_H - 124, SCREEN_W - 2 * (MARGIN - 6), 26)
        pygame.draw.rect(self.screen, UI_BG, rule_rect, border_radius=6)
        rule_surf = self.font.render(rule_line, True, TEXT_COLOR)
        self.screen.blit(rule_surf, (rule_rect.x+10, rule_rect.y+5))
        dt_text = f"AI depth {self.ai.completed_depth}/{self.ai.max_depth}  limit {self.ai.time_limit:.2f}s"
        dt_surf = self.font.render(dt_text, True, SUBTEXT_COLOR)
        self.screen.blit(dt_surf, (rule_rect.right - dt_surf.get_width() - 10, rule_rect.y + 5))

        # Center both control rows and size each button to fit its label.
        self.button_rects = {}
        btn_h = 34
        row1_y = SCREEN_H - 88
        row2_y = SCREEN_H - 48

        row1 = [
            ("new", "New Game", False),
            ("ai", f"AI: {'On' if self.ai_enabled else 'Off'}", self.ai_enabled),
            ("hotseat", f"Hotseat: {'On' if self.hotseat else 'Off'}", self.hotseat),
            ("suggest", "Suggest"),
            ("debug", f"Debug: {'On' if self.debug else 'Off'}", self.debug),
        ]
        row2 = [
            ("depth-", "− Depth"),
            ("depth+", "+ Depth"),
            ("rule-", "Rule Prev"),
            ("rule+", "Rule Next"),
        ]
        if self.swap_choice_pending:
            row2.append(("swap", "Swap Colors"))
        if self.swap2_request_available:
            row2.append(("ask2", "Ask 2 More"))
        if self.game_over and not self.show_result_overlay:
            row2.append(("result", "Show Result"))

        def draw_button_row(items, y):
            gap = 10
            widths = [max(88, self.button_font.size(item[1])[0] + 28) for item in items]
            total_width = sum(widths) + gap * max(0, len(items) - 1)
            available_width = SCREEN_W - 2 * MARGIN
            if total_width > available_width:
                scale = (available_width - gap * max(0, len(items) - 1)) / sum(widths)
                widths = [int(width * scale) for width in widths]
                total_width = sum(widths) + gap * max(0, len(items) - 1)
            x = (SCREEN_W - total_width) // 2
            for index, item in enumerate(items):
                key, label = item[:2]
                active = item[2] if len(item) > 2 else key == "result"
                rect = pygame.Rect(x, y, widths[index], btn_h)
                self.button_rects[key] = rect
                self.draw_button(label, rect, active=active)
                x += widths[index] + gap

        draw_button_row(row1, row1_y)
        draw_button_row(row2, row2_y)

        # debug overlay
        if self.debug:
            self.draw_debug_overlay()

    def draw_button(self, label, rect, active=False):
        mouse_over = rect.collidepoint(pygame.mouse.get_pos())
        fill = BUTTON_ACTIVE if active else BUTTON_BG
        if mouse_over:
            fill = BUTTON_HOVER if not active else (74, 132, 106)
        pygame.draw.rect(self.screen, fill, rect, border_radius=8)
        pygame.draw.rect(self.screen, BUTTON_BORDER, rect, 1, border_radius=8)
        label_surf = self.button_font.render(label, True, TEXT_COLOR)
        self.screen.blit(label_surf, label_surf.get_rect(center=rect.center))

    def draw_debug_overlay(self):
        x = SCREEN_W - 300
        y = 10
        w = 280
        h = 200
        pygame.draw.rect(self.screen, (10,10,10,180), (x-6, y-6, w+12, h+12), border_radius=8)
        pygame.draw.rect(self.screen, UI_BG, (x, y, w, h), border_radius=8)
        lines = [
            f"DEBUG",
            f"AI thinking: {self.ai_thinking}",
            f"Nodes: {self.ai.nodes}",
            f"AI depth: {self.ai.completed_depth}/{self.ai.max_depth}",
            f"AI last time: {self.last_ai_time:.3f}s",
            f"TT size: {len(self.ai.tt.table)}",
            f"Moves played: {len(self.board.moves)}",
            f"Available candidates: {len(generate_candidates(self.board))}",
            f"PV: " + " ".join(str(self.board.rc(m)) for m in (self.ai.best_line or [])),
        ]
        yy = y + 10
        for ln in lines:
            s = self.font.render(ln, True, TEXT_COLOR)
            self.screen.blit(s, (x+10, yy))
            yy += 20

    def mainloop(self):
        self.reset_game()
        while self.running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                elif event.type == AI_MOVE_EVENT:
                    self.handle_ai_result(event)
                elif event.type == pygame.MOUSEBUTTONDOWN:
                    if self.handle_button_click(event.pos):
                        continue
                    self.handle_click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE:
                        if self.ai_enabled and self.current_turn == self.ai.color:
                            self.run_ai_move()
                    elif event.key == pygame.K_s:
                        self.suggest()
                    elif event.key == pygame.K_d:
                        self.debug = not self.debug
                    elif event.key == pygame.K_r:
                        self.cycle_rule(1)
                    elif event.key == pygame.K_c and self.swap_choice_pending:
                        self.swap_colors()
                    elif event.key == pygame.K_n:
                        self.reset_game()
                    elif event.key == pygame.K_v and self.game_over:
                        self.show_result_overlay = not self.show_result_overlay
                        self.review_mode = not self.show_result_overlay

            # auto AI swap decisions
            self.handle_ai_swap_decision()
            # auto AI move if enabled
            if self.should_ai_move():
                self.run_ai_move()

            self.draw_board()
            pygame.display.flip()
            self.clock.tick(FPS)
        pygame.quit()
        sys.exit()

if __name__ == "__main__":
    gui = GUI()
    gui.mainloop()
