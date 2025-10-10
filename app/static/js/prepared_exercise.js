document.addEventListener('DOMContentLoaded', () => {
  const useTimeCheckbox = document.getElementById('use_time_limit');
  const timeFields = document.getElementById('time_fields');
  const questionsContainer = document.getElementById('questions_container');
  const addQuestionButton = document.getElementById('add-question');
  const template = document.getElementById('question-template');

  if (!questionsContainer || !template) {
    return;
  }

  const updateIndexes = () => {
    const cards = questionsContainer.querySelectorAll('.question-card');
    cards.forEach((card, index) => {
      const indexElement = card.querySelector('.question-index');
      if (indexElement) {
        indexElement.textContent = index + 1;
      }
      const removeButton = card.querySelector('[data-action="remove"]');
      if (removeButton) {
        removeButton.disabled = cards.length === 1;
      }
    });
  };

  const addQuestion = () => {
    const fragment = template.content.cloneNode(true);
    const card = fragment.querySelector('.question-card');
    questionsContainer.appendChild(card);
    updateIndexes();
  };

  questionsContainer.addEventListener('click', (event) => {
    const target = event.target;
    if (target instanceof HTMLElement && target.dataset.action === 'remove') {
      const card = target.closest('.question-card');
      if (card && questionsContainer.children.length > 1) {
        card.remove();
        updateIndexes();
      }
    }
  });

  if (addQuestionButton) {
    addQuestionButton.addEventListener('click', () => {
      addQuestion();
      questionsContainer.lastElementChild?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    });
  }

  if (useTimeCheckbox && timeFields) {
    useTimeCheckbox.addEventListener('change', () => {
      if (useTimeCheckbox.checked) {
        timeFields.hidden = false;
        timeFields.querySelectorAll('input').forEach((input) => {
          input.disabled = false;
        });
      } else {
        timeFields.hidden = true;
        timeFields.querySelectorAll('input').forEach((input) => {
          input.disabled = true;
          if (input instanceof HTMLInputElement) {
            input.value = input.id === 'limit_seconds' ? '0' : input.value;
          }
        });
      }
    });

    // Initialize hidden state
    useTimeCheckbox.dispatchEvent(new Event('change'));
  }

  addQuestion();
});
