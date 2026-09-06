const content = {
  checkpoint: {
    tag: 'CHECKPOINT INPUT',
    title: 'Intent is the missing half of recovery.',
    text: 'Entire Checkpoints preserve the decision context that Git diffs omit. Warden reads it locally to explain what the migration was trying to accomplish after it heals.',
    code: 'entire checkpoint explain <checkpoint-id> --short',
  },
  graph: {
    tag: 'PRE-FLIGHT EVIDENCE',
    title: 'Graph evidence is shown, not treated as certainty.',
    text: 'Before applying a migration, Warden runs Entire Graph impact analysis. If it is unavailable, the operator sees that limitation explicitly instead of receiving a false assurance.',
    code: 'entire graph impact --repo . --symbol demo_users --head --profile fast',
  },
  delta: {
    tag: 'LIVE DATABRICKS BEHAVIOR',
    title: 'Delta rejects the bad existing row.',
    text: 'The demo CHECK constraint validates existing Delta data at ADD CONSTRAINT time. The seeded legacy plan triggers DELTA_NEW_CHECK_CONSTRAINT_VIOLATION before the follow-up validation query.',
    code: "ALTER TABLE ... ADD CONSTRAINT ... CHECK (plan IN ('free', 'pro', 'enterprise'))",
  },
  heal: {
    tag: 'SAFE RECOVERY',
    title: 'Delta time travel returns the table to its known version.',
    text: 'Warden restores the pre-migration Delta version, records a sanitized healed result, and gives the operator the local-only explanation needed to write the corrected migration.',
    code: 'RESTORE TABLE warden.demo_users TO VERSION AS OF <pre_version>',
  },
};

const detail = document.querySelector('#stage-detail');
document.querySelectorAll('.flow-card').forEach((card) => {
  card.addEventListener('click', () => {
    document.querySelectorAll('.flow-card').forEach((item) => item.classList.remove('active'));
    card.classList.add('active');
    const stage = content[card.dataset.stage];
    detail.innerHTML = `<div class="detail-tag">${stage.tag}</div><h3>${stage.title}</h3><p>${stage.text}</p><code>${stage.code}</code>`;
  });
});
