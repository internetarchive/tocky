from collections.abc import Callable
import time
from typing import Generic, ParamSpec, TypeVar
from tocky.utils import ShareableState
from tocky.utils.expense_tracker import ExpenseEntry, ExpenseTracker
from tocky.utils.models import LLMModel
from openai.types.chat import ChatCompletion

TParams = TypeVar("TParams")

TDecoratorParams = ParamSpec("TDecoratorParams")
TDecoratorReturn = TypeVar("TDecoratorReturn")

class AbstractPhase(Generic[TParams]):
    name: str
    P: TParams
    S: ShareableState
    expense_tracker: ExpenseTracker | None

    job_id: int | None = None
    batch_id: int | None = None

    debug = True
    """
    When debug is set to true, extra helper variables could be set
    """

    def __init__(self):
        self.S = ShareableState()
        self.expense_tracker = None

    def log_debug(self, *args, **kwargs):
        if self.debug:
            print(*args, **kwargs)

    def log_expense(self, cost: int, duration: int, record: dict):
        if not self.expense_tracker:
            # Expense tracking not enabled
            return
    
        if not self.job_id:
            raise ValueError("job_id must be set to log expense")

        entry = ExpenseEntry(
            phase=self.name,
            toc_queue_id=self.job_id,
            batch_id=self.batch_id,
            cost=cost,
            duration=duration,
            record=record
        )

        self.expense_tracker.add_expense(entry)
    
    def log_llm_expense(self, model: LLMModel, func: Callable[TDecoratorParams, ChatCompletion]) -> Callable[TDecoratorParams, ChatCompletion]:
        """
        Wrap an LLM call to automatically log the expense.
        """
        def wrapper(*args, **kwargs):
            start = time.time()
            response = func(*args, **kwargs)
            end = time.time()

            assert model
            assert response.usage
            self.log_expense(
                cost=model.compute_price(response.usage),
                duration=int((end - start) * 1000),  # Convert to milliseconds
                record={
                    "model": model.model,
                    "prompt_tokens": response.usage.prompt_tokens,
                    "completion_tokens": response.usage.completion_tokens,
                    "total_tokens": response.usage.total_tokens,
                }
            )
            return response
        return wrapper