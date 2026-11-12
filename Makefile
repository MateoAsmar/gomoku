NAME := Gomoku
PYTHON ?= python3

.PHONY: all clean fclean re

all: $(NAME)

$(NAME): launcher.py gomoku.py
	cp launcher.py $(NAME)
	chmod +x $(NAME)

clean:
	rm -rf __pycache__

fclean: clean
	rm -f $(NAME)

re: fclean all
