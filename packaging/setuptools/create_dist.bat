@echo ............... CHANGING TO PROJECT ROOT ......................
cd ..\..

rmdir build /s /q

@echo ............... CREATING wheel ................................
C:\Python36-32\python.exe setup.py bdist_wheel -d packaging\setuptools

@echo ............... CREATING sdist ................................
C:\Python36-32\python.exe setup.py sdist --formats=gztar -d packaging\setuptools

cd packaging\setuptools
pause