const dom = require('jsdom');
const { JSDOM } = dom;
const { document } = (new JSDOM('<!DOCTYPE html><select id="test" data-entity="college" data-parent-class="college-select"><option value="">Select</option></select>')).window;
global.document = document;
global.window = document.defaultView;
global.HTMLElement = window.HTMLElement;
global.HTMLSelectElement = window.HTMLSelectElement;
global.HTMLInputElement = window.HTMLInputElement;
global.navigator = window.navigator;
global.Event = window.Event;
global.CustomEvent = window.CustomEvent;
global.DocumentFragment = window.DocumentFragment;

const TomSelect = require('./ts.js');

try {
    new TomSelect(document.getElementById('test'), {
        valueField: 'value',
        labelField: 'text',
        searchField: ['text'],
        sortField: { field: 'text', direction: 'asc' },
    });
    console.log('Success');
} catch (e) {
    console.log(e.stack);
}
