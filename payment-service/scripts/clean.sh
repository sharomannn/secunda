#!/bin/bash
set -e

echo "🗑️  Очистка Payment Processing Service..."
echo ""

read -p "Это удалит все контейнеры, volumes и данные. Продолжить? (y/N) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Отменено."
    exit 0
fi

echo "Остановка сервисов..."
docker-compose down -v

echo "Удаление образов..."
docker-compose rm -f

echo ""
echo "✅ Очистка завершена!"
echo ""
echo "Для нового запуска выполните: ./scripts/init.sh"
