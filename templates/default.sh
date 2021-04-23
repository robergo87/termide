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
