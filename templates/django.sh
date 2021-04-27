#!/bin/bash

termide reset
termide maximize
termide term_feed "tih tree 1" 0
termide term_scale -0.1
termide split h
termide resize_last 640 0 1
termide split v
termide resize_last 0 200 0
termide split h
termide resize_first 240 0 0
termide tab 3
termide split v

termide tab 0
termide term_feed "tih micro manage.py" 1
termide term_feed "source env/bin/activate" 3
termide term_feed "source env/bin/activate" 4


