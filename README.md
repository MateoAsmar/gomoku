# Gomoku

A 19×19 Gomoku game with a playable AI opponent, local hotseat mode, opening-rule variants, and move suggestions. Built with Python and Pygame.

## Features

- **AI opponent** using iterative-deepening negamax, alpha-beta pruning, principal-variation search, late-move reductions, and a Zobrist transposition table.
- **Tactical play** with immediate-win and threat-block checks, local candidate generation, move ordering, and a line-pattern evaluation function.
- **Four opening options**: Standard, Pro, Swap, and Swap2.
- **Capture rules**: bracket two opponent stones to capture the pair; five captured pairs win. A line of five also wins when it cannot be broken by a capture.
- **Hotseat mode** for two players at one keyboard, plus AI move suggestions when you want a hint.
- **Position review** after a game, with move numbers, winning line, final move, and captured stones highlighted.
- **Search diagnostics** for elapsed time, nodes, depth, principal variation, and transposition-table size.

## Requirements

- Python 3
- Pygame 2.6.1 or later, below version 3
- A desktop environment that can open a Pygame window

## Run

From the repository root:

~~~sh
python3 -m pip install -r requirements.txt
make
./Gomoku
~~~

You can also start the game without building the launcher:

~~~sh
python3 gomoku.py
~~~

The Makefile creates an executable launcher named Gomoku. The project has no external assets to download.

## How to play

Click an empty intersection to place a stone. Black moves first. In AI mode, the AI plays White by default. Turn on **Hotseat** to take turns locally, or turn off **AI** to play manually without a computer opponent.

### Rules

| Rule set | Opening |
| --- | --- |
| Standard | Normal alternating play. Double-three moves are restricted. |
| Pro | Black's first stone is placed in the center automatically. |
| Swap | After the first stone, White can switch colors. |
| Swap2 | Black, White, Black are placed first; White can swap, continue, or request two additional opening stones. |

A player wins by making a line of at least five stones or by capturing five pairs. The board fills to a draw if neither player wins first.

### Controls

| Input | Action |
| --- | --- |
| Mouse click | Place a stone or activate a button |
| **N** | Start a new game |
| **S** | Suggest a move for the side to move |
| **D** | Toggle search/debug details |
| **R** | Cycle opening rules |
| **C** | Accept the color swap when a swap decision is available |
| **V** | Show or hide the result panel after a game |
| **Space** | Start an AI move when it is the AI's turn |

The on-screen buttons provide the same game-mode, rule, depth, and review controls.

## How the AI searches

The AI searches candidate intersections near existing stones rather than scanning the whole board. It iteratively deepens a negamax search, orders moves, and prunes with alpha-beta and principal-variation techniques. A transposition table reuses previously evaluated positions. The default budget is two seconds per move, with a maximum search depth of ten plies; the completed depth depends on the position and available time.

The evaluator scores line patterns and capture progress. Before quiet moves, the search checks for immediate wins and direct blocks. These choices keep the game responsive while concentrating work on tactically relevant moves.

## Project files

~~~text
.
├── gomoku.py        # Board rules, AI search, and Pygame interface
├── launcher.py      # Entry point used by the Makefile
├── requirements.txt # Pygame dependency
└── Makefile         # Builds the ./Gomoku launcher
~~~

## Clean build artifacts

~~~sh
make clean   # remove Python bytecode cache
make fclean  # also remove the Gomoku launcher
make re      # clean and rebuild the launcher
~~~

This is a local desktop game. Online multiplayer, accounts, and saved game history are not part of this project.
