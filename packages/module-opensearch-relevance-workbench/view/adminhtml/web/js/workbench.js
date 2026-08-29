define([], function () {
    'use strict';

    return function (config, element) {
        var steps = ['readiness', 'snapshot', 'tune', 'judge', 'compare', 'activate'];
        var tabs = Array.prototype.slice.call(element.querySelectorAll('[data-osrw-step]'));
        var panels = Array.prototype.slice.call(element.querySelectorAll('[data-osrw-panel]'));
        var source = element.querySelector('.osrw-source');
        var currentStep;
        var compactTabs = window.matchMedia('(max-width: 1000px)');

        if (source) {
            Array.prototype.slice.call(source.querySelectorAll('[data-osrw-section]'))
                .sort(function (left, right) {
                    var stepDelta = steps.indexOf(left.dataset.osrwSection) - steps.indexOf(right.dataset.osrwSection);

                    return stepDelta || Number(left.dataset.osrwPriority || 50) - Number(right.dataset.osrwPriority || 50);
                })
                .forEach(function (section) {
                var panel = element.querySelector('[data-osrw-panel="' + section.dataset.osrwSection + '"]');

                if (panel) {
                    panel.appendChild(section);
                }
            });
            source.remove();
        }

        Array.prototype.slice.call(element.querySelectorAll('[data-osrw-secondary="true"]')).forEach(
            function (section, index) {
                var title = section.querySelector('.admin__fieldset-wrapper-title');
                var content = section.querySelector('.admin__fieldset-wrapper-content');
                var button = document.createElement('button');
                var contentId = 'osrw-secondary-' + index;

                if (!title || !content) {
                    return;
                }

                content.id = contentId;
                content.hidden = true;
                button.type = 'button';
                button.className = 'osrw-section-toggle';
                button.setAttribute('aria-controls', contentId);
                button.setAttribute('aria-expanded', 'false');
                button.textContent = 'Show details';
                button.addEventListener('click', function () {
                    var expanded = button.getAttribute('aria-expanded') === 'true';

                    button.setAttribute('aria-expanded', expanded ? 'false' : 'true');
                    button.textContent = expanded ? 'Show details' : 'Hide details';
                    content.hidden = expanded;
                });
                title.appendChild(button);
            }
        );

        Array.prototype.slice.call(element.querySelectorAll('table.data-grid')).forEach(function (table) {
            var body = table.tBodies[0];
            var headerCells = table.querySelectorAll('thead th');
            var row;
            var cell;

            if (!body || body.rows.length !== 0) {
                return;
            }

            row = body.insertRow();
            cell = row.insertCell();
            cell.colSpan = Math.max(headerCells.length, 1);
            cell.className = 'osrw-empty-row';
            cell.textContent = 'No records yet.';
        });

        function stepFromHash() {
            var value = window.location.hash.replace(/^#/, '');

            return steps.indexOf(value) === -1 ? null : value;
        }

        function selectStep(step, updateHistory) {
            if (steps.indexOf(step) === -1) {
                step = 'readiness';
            }

            tabs.forEach(function (tab) {
                var selected = tab.dataset.osrwStep === step;
                tab.setAttribute('aria-selected', selected ? 'true' : 'false');
                tab.setAttribute('tabindex', selected ? '0' : '-1');
            });

            panels.forEach(function (panel) {
                var selected = panel.dataset.osrwPanel === step;
                panel.hidden = !selected;

                if (selected && currentStep !== step) {
                    panel.classList.remove('is-entering');
                    window.requestAnimationFrame(function () {
                        panel.classList.add('is-entering');
                    });
                }
            });

            currentStep = step;

            if (updateHistory && window.location.hash !== '#' + step) {
                window.history.replaceState(null, '', window.location.pathname + window.location.search + '#' + step);
            }
        }

        tabs.forEach(function (tab, index) {
            tab.addEventListener('click', function () {
                selectStep(tab.dataset.osrwStep, true);
            });

            tab.addEventListener('keydown', function (event) {
                var targetIndex = index;

                if (event.key === 'ArrowDown' || event.key === 'ArrowRight') {
                    targetIndex = (index + 1) % tabs.length;
                } else if (event.key === 'ArrowUp' || event.key === 'ArrowLeft') {
                    targetIndex = (index - 1 + tabs.length) % tabs.length;
                } else if (event.key === 'Home') {
                    targetIndex = 0;
                } else if (event.key === 'End') {
                    targetIndex = tabs.length - 1;
                } else {
                    return;
                }

                event.preventDefault();
                tabs[targetIndex].focus();
                selectStep(tabs[targetIndex].dataset.osrwStep, true);
            });
        });

        window.addEventListener('hashchange', function () {
            selectStep(stepFromHash() || currentStep || 'readiness', false);
        });

        function updateOrientation() {
            var tablist = element.querySelector('[role="tablist"]');

            if (tablist) {
                tablist.setAttribute('aria-orientation', compactTabs.matches ? 'horizontal' : 'vertical');
            }
        }

        compactTabs.addEventListener('change', updateOrientation);
        updateOrientation();

        element.classList.add('is-ready');
        selectStep(stepFromHash() || element.dataset.osrwRecommendedStep || 'readiness', false);
    };
});
