#!/bin/bash

SERVICE=${1:-all}

case $SERVICE in
  api)
    docker-compose logs -f api
    ;;
  consumer)
    docker-compose logs -f consumer
    ;;
  outbox)
    docker-compose logs -f outbox-publisher
    ;;
  postgres)
    docker-compose logs -f postgres
    ;;
  rabbitmq)
    docker-compose logs -f rabbitmq
    ;;
  all)
    docker-compose logs -f
    ;;
  *)
    echo "Использование: $0 [api|consumer|outbox|postgres|rabbitmq|all]"
    exit 1
    ;;
esac
