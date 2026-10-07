import test from 'node:test';
import assert from 'node:assert/strict';

import {
  mergeCreatorDirection,
  splitDirectionLines,
} from '../creator-direction.js';

test('splitDirectionLines trims blanks and keeps meaningful preserve/avoid items', () => {
  assert.deepEqual(
    splitDirectionLines(' handheld movement \n\n long pause before final line '),
    ['handheld movement', 'long pause before final line']
  );
});

test('mergeCreatorDirection adds supplied individuality signals to Workshop payload', () => {
  const payload = mergeCreatorDirection(
    {
      situation: 'Edit my birthday video',
      goal: 'Make it feel intentional',
      output_type: 'social_content',
    },
    {
      creative_intent: ' intimate and nostalgic ',
      creator_context: ' personal memory, not branded content ',
      preserve: 'handheld movement\nlong pause before final line',
      avoid: 'generic cinematic transitions\noverly polished pacing',
    }
  );

  assert.equal(payload.creative_intent, 'intimate and nostalgic');
  assert.equal(payload.creator_context, 'personal memory, not branded content');
  assert.deepEqual(payload.preserve, [
    'handheld movement',
    'long pause before final line',
  ]);
  assert.deepEqual(payload.avoid, [
    'generic cinematic transitions',
    'overly polished pacing',
  ]);
});

test('mergeCreatorDirection leaves an ordinary Workshop payload ordinary when no signals are supplied', () => {
  const original = {
    situation: 'Compare two frameworks',
    goal: 'Explain the difference',
    output_type: 'knowledge_answer',
  };

  assert.deepEqual(mergeCreatorDirection(original, {}), original);
});
