import dramatiq
from dramatiq.brokers.rabbitmq import RabbitmqBroker

from program.queue.broker import verify_broker_config


def test_verify_broker_config_with_declared_false():
    # Create a broker instance without connecting; just set attribute we care about.
    b = RabbitmqBroker(url="amqp://guest:guest@localhost:5672/", declare_queues=False)
    dramatiq.set_broker(b)

    assert verify_broker_config(strict=False) is True
    # Also sanity check attribute
    assert getattr(dramatiq.get_broker(), "declare_queues", None) is False

