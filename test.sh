i=1
while [ 1 ]
do
	echo $i
	echo "start run"
	sleep 1
	pypy3 simpy_simulation.py
	i=$((i + 1))
	echo "start sleep"
	sleep 5
done
