# Gomoku

Gomoku is a 19×19 Pygame game with an AI opponent and a hotseat suggestion mode.

## Run

Install the dependency with `python3 -m pip install -r requirements.txt`, then run
`make` and launch `./Gomoku` (or run `python3 Gomoku`).

## Rules and controls

The standard game uses five-or-more-in-a-row wins, pair captures, a five-pair
capture win, double-three restrictions, and the subject's capture response to a
five. The rule selector also offers Pro, Swap, and Swap2 openings.

Click an intersection to place a stone. The buttons switch AI and hotseat play,
request a move suggestion, start a new game, or change the opening rule. The
interface displays AI search time, captures, and the completed/target search
depth. After a win or draw, choose **View Board** to inspect the final position
with move numbers and the winning move marked. Capture wins also mark the stones
removed by the final move. Choose **Show Result** or press `V` to bring the
result panel back. Debug mode shows the principal variation and search statistics.

## AI

The AI uses iterative deepening negamax with alpha-beta pruning, principal
variation search and late move reductions, a Zobrist transposition table,
immediate-win and threat-block checks, local candidate generation with selective
move ordering, and a line-pattern heuristic that includes capture progress. It
searches up to 10 plies with a 2 second default budget; the completed depth
depends on the position and is shown in the interface.
