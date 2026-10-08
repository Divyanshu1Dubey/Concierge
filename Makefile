node:
  test:
    - npm run type-check
    - npm run lint
  build:
    - npm run build
  test:
    - npm run test

python:
  lint:
    - black --check backend/
    - flake8 backend/
  test:
    - pytest backend/tests/ --cov=apps --cov-report=xml

docker:
  build:
    - docker compose build
  test:
    - docker compose run --rm backend pytest
