// pet_tags.js — loaded as static file, no Jinja required
document.addEventListener('DOMContentLoaded', function () {

    var tagDisplay = document.getElementById('tag-display');
    if (!tagDisplay) return; // not on a pet detail page

    // Derive save URL from current path: /admin/pets/29/detail → /admin/pets/29/tags
    var savePath = window.location.pathname.replace(/\/detail\/?$/, '/tags');

    // Read initial tags from data attribute on tag-display div
    var raw = tagDisplay.getAttribute('data-initial-tags') || '';
    var currentTags = raw ? raw.split(',').map(function (t) { return t.trim(); }).filter(Boolean) : [];

    var TAG_WARN    = ['Dog Aggressive','Not Dog Friendly','People Shy','Escape Artist','Dominant','Requires Separate Kennel','Needs Medication','Diabetic','Post-Surgery'];
    var TAG_INFO    = ['Senior','Anxious','Special Diet','Large Breed','Intact Male','Intact Female','Puppy','Deaf','Blind'];
    var TAG_SUCCESS = ['Free Bath Included','VIP','Long-Term Guest','First Stay'];

    function getTagStyle(t) {
        if (TAG_WARN.indexOf(t)    > -1) return 'background:#dc3545;color:white;border:none;';
        if (TAG_INFO.indexOf(t)    > -1) return 'background:#0d6efd;color:white;border:none;';
        if (TAG_SUCCESS.indexOf(t) > -1) return 'background:#198754;color:white;border:none;';
        return 'background:#6c757d;color:white;border:none;';
    }

    function renderTags() {
        if (currentTags.length === 0) {
            tagDisplay.innerHTML = '<span class="text-muted" style="font-size:0.85rem;">No tags added yet.</span>';
        } else {
            tagDisplay.innerHTML = currentTags.map(function (tag) {
                return '<span class="badge d-inline-flex align-items-center gap-1 px-2 py-1" style="' + getTagStyle(tag) + 'font-size:0.82rem;">' +
                    tag +
                    '<button type="button" class="btn-close btn-close-white ms-1" style="font-size:0.55rem;" data-remove-tag="' + tag.replace(/"/g, '&quot;') + '"></button>' +
                    '</span>';
            }).join('');
        }
        document.querySelectorAll('.suggestion-btn').forEach(function (btn) {
            var t = btn.getAttribute('data-tag');
            btn.disabled      = currentTags.indexOf(t) > -1;
            btn.style.opacity = currentTags.indexOf(t) > -1 ? '0.4' : '1';
        });
    }

    function saveTags() {
        fetch(savePath, {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ tags: currentTags })
        }).then(function () {
            var ind = document.getElementById('tag-save-indicator');
            if (ind) {
                ind.style.display = 'inline';
                setTimeout(function () { ind.style.display = 'none'; }, 2000);
            }
        }).catch(function (e) { console.error('Tag save failed', e); });
    }

    function addTag(tag) {
        if (!tag || currentTags.indexOf(tag) > -1) return;
        currentTags.push(tag);
        renderTags();
        saveTags();
    }

    function removeTag(tag) {
        currentTags = currentTags.filter(function (t) { return t !== tag; });
        renderTags();
        saveTags();
    }

    // Event delegation — handles suggestion buttons AND remove buttons
    document.addEventListener('click', function (e) {
        // Suggestion button
        var suggBtn = e.target.closest('.suggestion-btn');
        if (suggBtn) {
            e.preventDefault();
            addTag(suggBtn.getAttribute('data-tag'));
            return;
        }
        // Remove (×) button on a tag badge
        var removeBtn = e.target.closest('[data-remove-tag]');
        if (removeBtn) {
            e.preventDefault();
            removeTag(removeBtn.getAttribute('data-remove-tag'));
            return;
        }
        // Add custom tag button
        if (e.target.id === 'add-custom-tag-btn' || e.target.closest('#add-custom-tag-btn')) {
            e.preventDefault();
            addCustomTag();
        }
    });

    function addCustomTag() {
        var input = document.getElementById('custom-tag-input');
        if (input && input.value.trim()) {
            addTag(input.value.trim());
            input.value = '';
        }
    }

    var customInput = document.getElementById('custom-tag-input');
    if (customInput) {
        customInput.addEventListener('keydown', function (e) {
            if (e.key === 'Enter') { e.preventDefault(); addCustomTag(); }
        });
    }

    renderTags();
});
