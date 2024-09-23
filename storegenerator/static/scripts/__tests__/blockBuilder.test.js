import { buildBlock } from '../blockBuilder.js';

// Mock the DOM methods that buildBlock might use
document.createElement = jest.fn().mockImplementation((tag) => {
    const element = {
        setAttribute: jest.fn(),
        appendChild: jest.fn(),
        classList: {
            add: jest.fn()
        },
        style: {},
        value: ''
    };
    return element;
});

document.querySelectorAll = jest.fn().mockReturnValue([]);

describe('buildBlock', () => {
    test('handles undefined block gracefully', () => {
        const result = buildBlock(undefined, 'someId');
        expect(result).toBeNull();
    });

    test('builds a title block correctly', () => {
        const mockBlock = {
            type: 'title',
            title: 'Test Title',
            description: 'Test Description'
        };
        const result = buildBlock(mockBlock, 'titleId');
        expect(result).toBeDefined();
        expect(document.createElement).toHaveBeenCalledWith('div');
        expect(document.createElement).toHaveBeenCalledWith('h1');
        expect(document.createElement).toHaveBeenCalledWith('textarea');
    });

    // Add more tests for other block types
});