#!/bin/bash

termide bind Alt+Up termide move u
termide bind Alt+Down termide move d
termide bind Alt+Left termide move l
termide bind Alt+Right termide move r

termide bind Control+Shift+V termide split v
termide bind Control+Shift+H termide split h

termide bind Control+Shift+Left termide resize -10 0
termide bind Control+Shift+Right termide resize 10 0
termide bind Control+Shift+Up termide resize 0 -10
termide bind Control+Shift+Down termide resize 0 10

termide bind Control+Shift+Less termide term_prev
termide bind Control+Shift+Greater termide term_next
termide bind Control+Shift+X termide term_close
termide bind Control+Shift+N termide term_add default

termide bind Control+Shift+A termide term_scale +0.1
termide bind Control+Shift+Z termide term_scale -0.1
termide bind Control+Shift+Q termide term_set_scale 1


