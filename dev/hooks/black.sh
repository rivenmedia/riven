python_files=$(echo $@ | grep '\.py$')

black $python_files && git add $python_files
