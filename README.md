# Crashing my 4750G on Asrock DeskMini X300

## Install

requirements: pypy3, gcc-fortran

should work with python3 too, but it seems to trigger faster with pypy3 in my experience.

```bash
pypy3 -m ensurepip
pypy3 -m pip install -r requirements.txt
```

## Run
```bash
bash test.sh
```

I never get past 9
