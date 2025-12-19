let isWaitingForResponse = false;
let currentThinkingContainer = null;
let stepCounter = 0;
let hasUsedTools = false;
let editingMessage = null;
let allMessages = [];
let responseStartTime = null;
let toolsUsed = new Set();
let currentSessionId = null;
let ws = null;

document.addEventListener('DOMContentLoaded', () => {
    loadChatHistory();
});

function connectWebSocket(sessionId) {
    closeWebSocket();
    
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/session/${sessionId}`;
    
    console.log('Connecting to WebSocket:', wsUrl);
    ws = new WebSocket(wsUrl);
    
    ws.onopen = () => {
        console.log('WebSocket connected');
    };
    
    ws.onclose = (event) => {
        console.log('WebSocket closed:', event.code, event.reason);
        ws = null;
    };
    
    ws.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
    
    ws.onmessage = (event) => {
        handleWebSocketMessage(event.data);
    };
}

function closeWebSocket() {
    if (ws) {
        ws.close();
        ws = null;
    }
}

async function loadChatHistory() {
    console.log('Loading chat history...');
    try {
        const response = await fetch('/sessions');
        console.log(response);
        const data = await response.json();
        
        const chatHistoryContainer = document.querySelector('.chat-history');
        if (!chatHistoryContainer) return;
        
        chatHistoryContainer.innerHTML = '';
        
        if (data.sessions && data.sessions.length > 0) {
            const validSessions = data.sessions;
            
            validSessions.forEach(session => {
                const item = document.createElement('div');
                item.className = 'chat-history-item';
                item.dataset.sessionId = session.session_id;
                console.log(session);
                const displayName = session.session_name || 
                    (session.summary ? session.summary.substring(0, 30) + '...' : 'Untitled Chat');
                
                const textSpan = document.createElement('span');
                textSpan.className = 'chat-item-text';
                textSpan.textContent = displayName;
                textSpan.onclick = (e) => {
                    e.stopPropagation();
                    loadSession(session.session_id);
                };
                
                
                const deleteBtn = document.createElement('button');
                deleteBtn.type = 'button';
                deleteBtn.className = 'chat-delete-btn';
                deleteBtn.title = 'Delete chat';
                deleteBtn.innerHTML = `
                    <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                        <path d="M3 6h18"></path>
                        <path d="M19 6v14c0 1-1 2-2 2H7c-1 0-2-1-2-2V6"></path>
                        <path d="M8 6V4c0-1 1-2 2-2h4c1 0 2 1 2 2v2"></path>
                    </svg>
                `;
                deleteBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    e.stopImmediatePropagation();
                    const sessionIdToDelete = session.session_id;
                        deleteSession(sessionIdToDelete);
                
                    return false;
                });

                item.appendChild(textSpan);
                item.appendChild(deleteBtn);
                
                if (session.session_id === currentSessionId) {
                    item.classList.add('active');
                }
                
                chatHistoryContainer.appendChild(item);
            });
        } else {
            chatHistoryContainer.innerHTML = '<div class="chat-history-item" style="color: #6b7280;">No chat history</div>';
        }
    } catch (err) {
        console.error('Error loading chat history:', err);
    }
}

async function deleteSession(sessionId) {
    try {
        const response = await fetch(`/sessions/${sessionId}`, {
            method: 'DELETE'
        });
        const data = await response.json();
        
        if (data.status === 'deleted') {
            if (sessionId === currentSessionId) {
                startNewChat();
            }
            loadChatHistory();
        } else {
            console.error('Failed to delete:', data.error);
        }
    } catch (err) {
        console.error('Error deleting session:', err);
    }
}

async function loadSession(sessionId) {
    try {
        const response = await fetch(`/sessions/${sessionId}`);
        const data = await response.json();
        
        if (data.error) {
            console.error('Error loading session:', data.error);
            return;
        }
        
        currentSessionId = sessionId;
        
        messagesContainer.innerHTML = '';
        messagesContainer.appendChild(welcomeScreen);
        
        if (data.history && data.history.length > 0) {
            welcomeScreen.style.display = 'none';
            
            data.history.forEach(msg => {
                addMessage(msg.content, msg.role === 'user' ? 'user' : 'assistant');
            });
        } else {
            welcomeScreen.style.display = 'flex';
        }
        
        document.querySelectorAll('.chat-history-item').forEach(item => {
            item.classList.remove('active');
            if (item.dataset.sessionId === sessionId) {
                item.classList.add('active');
            }
        });
        
        stepCounter = 0;
        hasUsedTools = false;
        allMessages = [];
        responseStartTime = null;
        currentThinkingContainer = null;
        toolsUsed.clear();
        
    } catch (err) {
        console.error('Error loading session:', err);
    }
}

function toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    sidebar.classList.toggle('collapsed');
}

function copyMessage(messageElement) {
    const content = messageElement.querySelector('.message-content').textContent;
    navigator.clipboard.writeText(content).then(() => {
        showCopyNotification();
    }).catch(err => {
        console.error('Failed to copy: ', err);
    });
}

function showCopyNotification() {
    const notification = document.getElementById('copyNotification');
    notification.classList.add('show');
    setTimeout(() => {
        notification.classList.remove('show');
    }, 2000);
}

function editMessage(messageElement) {
    if (editingMessage) {
        cancelEdit();
    }

    editingMessage = messageElement;
    const contentDiv = messageElement.querySelector('.message-content');
    const originalText = contentDiv.textContent;

    messageElement.classList.add('editing');
    contentDiv.innerHTML = `
        <textarea class="edit-input" id="editInput">${originalText}</textarea>
        <div class="edit-actions">
            <button class="edit-btn save" onclick="saveEdit()">Save</button>
            <button class="edit-btn cancel" onclick="cancelEdit()">Cancel</button>
        </div>
    `;

    const textarea = document.getElementById('editInput');
    textarea.focus();
    textarea.setSelectionRange(textarea.value.length, textarea.value.length);
}

function saveEdit() {
    if (!editingMessage) return;

    const textarea = document.getElementById('editInput');
    const newText = textarea.value.trim();

    if (newText) {
        const messagesContainer = document.getElementById('messagesContainer');
        const allElements = Array.from(messagesContainer.children);
        const editedElementIndex = allElements.indexOf(editingMessage);

        const elementsToRemove = allElements.slice(editedElementIndex + 1);
        elementsToRemove.forEach(element => {
            if (element.classList.contains('thinking-container') || 
                element.classList.contains('message') || 
                element.classList.contains('welcome-screen')) {
                element.remove();
            }
        });

        currentThinkingContainer = null;

        editingMessage.classList.remove('editing');
        const contentDiv = editingMessage.querySelector('.message-content');
        contentDiv.textContent = newText;

        editingMessage = null;

        const welcomeScreen = document.getElementById('welcomeScreen');
        welcomeScreen.style.display = 'none';

        responseStartTime = null;
        streamResponse(newText);
    } else {
        cancelEdit();
    }
}

function cancelEdit() {
    if (!editingMessage) return;

    const contentDiv = editingMessage.querySelector('.message-content');
    const textarea = document.getElementById('editInput');
    const originalText = textarea.value;

    editingMessage.classList.remove('editing');
    contentDiv.textContent = originalText;
    editingMessage = null;
}

function parseMarkdown(text) {
    return text
        .replace(/^### (.*$)/gim, '<h3>$1</h3>')
        .replace(/^## (.*$)/gim, '<h2>$1</h2>')
        .replace(/^# (.*$)/gim, '<h1>$1</h1>')
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/\*(.*?)\*/g, '<em>$1</em>')
        .replace(/\`\`\`(.*?)\`\`\`/gs, '<pre><code>$1</code></pre>')
        .replace(/`(.*?)`/g, '<code>$1</code>')
        .replace(/^\* (.*$)/gim, '<li>$1</li>')
        .replace(/^- (.*$)/gim, '<li>$1</li>')
        .replace(/^• (.*$)/gim, '<li>$1</li>')
        .replace(/^\d+\. (.*$)/gim, '<li>$1</li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');
}

function wrapListItems(html) {
    return html.replace(/(<li>.*?<\/li>(?:\s*<li>.*?<\/li>)*)/gs, '<ul>$1</ul>');
}

function createTopicSuggestions(text) {
    const topicPattern = /\*([^*:]+):\*\*(.*?)(?=\*|$)/g;
    return text.replace(topicPattern, (match, title, description) => {
        return `<div class="topic-suggestion" onclick="sendQuickMessage('${title.trim()}')">
            <div class="topic-title">${title.trim()}</div>
            <div class="topic-description">${description.trim()}</div>
        </div>`;
    });
}

function autoResize(textarea) {
    textarea.style.height = 'auto';
    const newHeight = Math.min(Math.max(textarea.scrollHeight, 24), 200);
    textarea.style.height = newHeight + 'px';
}

function startNewChat() {
    closeWebSocket();
    
    const messagesContainer = document.getElementById('messagesContainer');
    const welcomeScreen = document.getElementById('welcomeScreen');

    fetch("/new_chat", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        }
    })
    .then(res => res.json())
    .then(data => {
        console.log(data.status);
        currentSessionId = data.session_id;
        setTimeout(loadChatHistory, 500);
    })
    .catch(err => console.error("Error:", err));

    messagesContainer.innerHTML = '';
    messagesContainer.appendChild(welcomeScreen);
    welcomeScreen.style.display = 'flex';

    stepCounter = 0;
    hasUsedTools = false;
    allMessages = [];
    responseStartTime = null;
    currentThinkingContainer = null;
    toolsUsed.clear();
}

function sendQuickMessage(message) {
    document.getElementById('messageInput').value = message;
    sendMessage();
}

function handleKeyPress(event) {
    if (event.key === 'Enter' && !event.shiftKey) {
        event.preventDefault();
        sendMessage();
    }
}

function sendMessage() {
    const messageInput = document.getElementById('messageInput');
    const message = messageInput.value.trim();

    if (!message || isWaitingForResponse) return;

    const welcomeScreen = document.getElementById('welcomeScreen');
    welcomeScreen.style.display = 'none';

    responseStartTime = Date.now();

    addMessage(message, 'user');
    messageInput.value = '';
    messageInput.style.height = 'auto';

    hasUsedTools = false;
    toolsUsed.clear();

    streamResponse(message);
}

function addMessage(content, sender, isHtml = false) {
    const messagesContainer = document.getElementById('messagesContainer');
    const messageDiv = document.createElement('div');
    messageDiv.className = `message ${sender} fade-in`;

    const messageWrapper = document.createElement('div');
    messageWrapper.className = 'message-wrapper';

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    if (isHtml) {
        contentDiv.innerHTML = content;
    } else {
        contentDiv.textContent = content;
    }

    const actionsDiv = document.createElement('div');
    actionsDiv.className = 'message-actions';

    if (sender === 'user') {
        actionsDiv.innerHTML = `
            <button class="action-btn" onclick="copyMessage(this.closest('.message'))" title="Copy">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" stroke="currentColor" stroke-width="2" fill="none"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" fill="none"/>
                </svg>
            </button>
            <button class="action-btn" onclick="editMessage(this.closest('.message'))" title="Edit">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" stroke="currentColor" stroke-width="2" fill="none"/>
                    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" stroke="currentColor" stroke-width="2" fill="none"/>
                </svg>
            </button>
        `;
    } else {
        actionsDiv.innerHTML = `
            <button class="action-btn" onclick="copyMessage(this.closest('.message'))" title="Copy">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                    <rect x="9" y="9" width="13" height="13" rx="2" ry="2" stroke="currentColor" stroke-width="2" fill="none"/>
                    <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" fill="none"/>
                </svg>
            </button>
        `;
    }

    messageWrapper.appendChild(contentDiv);
    messageWrapper.appendChild(actionsDiv);
    messageDiv.appendChild(messageWrapper);
    messagesContainer.appendChild(messageDiv);
    messagesContainer.scrollTop = messagesContainer.scrollHeight;

    allMessages.push({ content, sender, element: messageDiv });
}

function createThinkingContainer() {
    const messagesContainer = document.getElementById('messagesContainer');
    const thinkingDiv = document.createElement('div');
    thinkingDiv.className = 'thinking-container fade-in';

    const thinkingWrapper = document.createElement('div');
    thinkingWrapper.className = 'thinking-wrapper';

    thinkingWrapper.innerHTML = `
        <div class="thinking-header" onclick="toggleThinking(this)">
            <div class="thinking-header-left">
                <span class="thinking-loader"></span>
                <span class="analyzing-text">Thinking...</span>
            </div>
            <svg class="thinking-toggle" width="14" height="14" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                <path d="M6 9l6 6 6-6" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
        </div>
        <div class="thinking-content">
            <div class="thinking-steps" id="thinkingSteps"></div>
        </div>
    `;

    thinkingDiv.appendChild(thinkingWrapper);
    messagesContainer.appendChild(thinkingDiv);
    scrollToBottom();

    stepCounter = 0;
    return thinkingDiv;
}

function toggleThinking(headerElement) {
    const wrapper = headerElement.parentElement;
    const content = wrapper.querySelector('.thinking-content');
    const toggle = wrapper.querySelector('.thinking-toggle');

    if (content.classList.contains('expanded')) {
        content.classList.remove('expanded');
        toggle.classList.remove('expanded');
    } else {
        content.classList.add('expanded');
        toggle.classList.add('expanded');
    }
}

function addThinkingStep(type, data) {
    if (!currentThinkingContainer) return;

    const stepsContainer = currentThinkingContainer.querySelector('#thinkingSteps');
    const stepDiv = document.createElement('div');
    stepDiv.className = `thinking-step fast-fade-in`;

    if (data.tool_name !== "final_answer") {
        hasUsedTools = true;
        toolsUsed.add(data.tool_name);

        switch(type) {
            case 'tool-use':
                if (data.tool_name === 'WebSearch') {
                    updateThinkingHeader('search');
                    stepDiv.innerHTML = `
                        <span class="step-label">Query:</span><span class="step-value">${data.tool_args.query}</span>
                    `;
                } else {
                    stepDiv.innerHTML = `
                        <span class="step-label">Using:</span><span class="step-value">${data.tool_name}</span>
                    `;
                }
                break;

            case 'tool-output':
                if (data.tool_name === 'WebSearch') {
                    try {
                        const results = JSON.parse(data.output);
                        if (Array.isArray(results) && results.length > 0) {
                            const searchResultsHtml = results.map(result => `
                                <div class="search-result">
                                    <div class="search-result-icon">
                                        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                            <circle cx="11" cy="11" r="8" stroke="currentColor" stroke-width="2" fill="none"/>
                                            <path d="M21 21l-4.35-4.35" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                                        </svg>
                                    </div>
                                    <div class="search-result-content">
                                        <a href="${result.url}" target="_blank" class="search-result-title">${result.title}</a>
                                        <div class="search-result-url">${new URL(result.url).hostname}</div>
                                    </div>
                                </div>
                            `).join('');

                            stepDiv.innerHTML = `
                                <div style="margin-bottom: 8px;">
                                    <span class="step-label">Found ${results.length} sources:</span>
                                </div>
                                ${searchResultsHtml}
                            `;
                        } else {
                            stepDiv.innerHTML = `
                                <span class="step-label">Search:</span><span class="step-value">No results found</span>
                            `;
                        }
                    } catch (e) {
                        stepDiv.innerHTML = `
                            <span class="step-label">Search:</span><span class="step-value">Results received</span>
                        `;
                    }
                } else {
                    stepDiv.innerHTML = `
                        <span class="step-label">Result:</span><span class="step-value">${JSON.stringify(data.output).substring(0, 80)}</span>
                    `;
                }
                break;

            case 'reasoning':
                stepDiv.innerHTML = `
                    <span class="step-label">Thinking:</span><span class="step-value">${data.content.substring(0, 80)}...</span>
                `;
                break;
        }

        stepsContainer.appendChild(stepDiv);
        scrollToBottom();
    }
}

function updateThinkingHeader(type) {
    if (!currentThinkingContainer) return;

    const thinkingHeader = currentThinkingContainer.querySelector('.thinking-header-left');
    const loader = thinkingHeader.querySelector('.thinking-loader, .search-loader');
    const text = thinkingHeader.querySelector('.analyzing-text, .searching-text');

    if (type === 'search') {
        if (loader) {
            loader.className = 'search-loader';
        }
        if (text) {
            text.className = 'searching-text';
            text.textContent = 'Searching...';
        }
    } else {
        if (loader) {
            loader.className = 'thinking-loader';
        }
        if (text) {
            text.className = 'analyzing-text';
            text.textContent = 'Thinking...';
        }
    }
}

function scrollToBottom() {
    const messagesContainer = document.getElementById('messagesContainer');
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function streamResponse(message) {
    isWaitingForResponse = true;
    document.getElementById('sendBtn').disabled = true;

    if (!responseStartTime) {
        responseStartTime = Date.now();
    }

    if (!currentSessionId) {
        currentSessionId = crypto.randomUUID();
    }

    if (!ws || ws.readyState !== WebSocket.OPEN) {
        connectWebSocket(currentSessionId);
        const checkConnection = setInterval(() => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                clearInterval(checkConnection);
                ws.send(JSON.stringify({
                    type: 'message',
                    content: message
                }));
            }
        }, 50);
    } else {
        ws.send(JSON.stringify({
            type: 'message',
            content: message
        }));
    }
}

let wsAssistantMessageDiv = null;
let wsAssistantContentDiv = null;
let wsResponseText = '';

function handleWebSocketMessage(data) {
    const messagesContainer = document.getElementById('messagesContainer');
    
    try {
        const parsed = JSON.parse(data);
        console.log('WS message:', parsed);

        switch(parsed.type) {
            case 'thinking_start':
                currentThinkingContainer = createThinkingContainer();
                wsAssistantMessageDiv = null;
                wsAssistantContentDiv = null;
                wsResponseText = '';
                break;

            case 'token':
                if (!wsAssistantMessageDiv) {
                    wsAssistantMessageDiv = document.createElement('div');
                    wsAssistantMessageDiv.className = 'message assistant fade-in';

                    const messageWrapper = document.createElement('div');
                    messageWrapper.className = 'message-wrapper';

                    wsAssistantContentDiv = document.createElement('div');
                    wsAssistantContentDiv.className = 'message-content';

                    const actionsDiv = document.createElement('div');
                    actionsDiv.className = 'message-actions';
                    actionsDiv.innerHTML = `
                        <button class="action-btn" onclick="copyMessage(this.closest('.message'))" title="Copy">
                            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                                <rect x="9" y="9" width="13" height="13" rx="2" ry="2" stroke="currentColor" stroke-width="2" fill="none"/>
                                <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" stroke="currentColor" stroke-width="2" fill="none"/>
                            </svg>
                        </button>
                    `;

                    messageWrapper.appendChild(wsAssistantContentDiv);
                    messageWrapper.appendChild(actionsDiv);
                    wsAssistantMessageDiv.appendChild(messageWrapper);
                    messagesContainer.appendChild(wsAssistantMessageDiv);
                }
                wsResponseText += parsed.content;
                wsAssistantContentDiv.textContent = wsResponseText;
                wsAssistantContentDiv.classList.add('fast-fade-in');
                scrollToBottom();
                break;

            case 'tool_use':
                hasUsedTools = true;
                toolsUsed.add(parsed.tool_name);
                addThinkingStep('tool-use', parsed);
                break;

            case 'tool_output':
                addThinkingStep('tool-output', parsed);
                break;

            case 'thinking_end':
                break;

            case 'done':
                isWaitingForResponse = false;
                document.getElementById('sendBtn').disabled = false;

                let seconds = 0;
                if (responseStartTime) {
                    const responseEndTime = Date.now();
                    const responseTime = responseEndTime - responseStartTime;
                    seconds = (responseTime / 1000).toFixed(1);
                    responseStartTime = null;
                }

                if (wsAssistantContentDiv && wsResponseText) {
                    let processedResponse = parseMarkdown(wsResponseText);
                    processedResponse = wrapListItems(processedResponse);
                    processedResponse = createTopicSuggestions(processedResponse);

                    if (!processedResponse.includes('<p>')) {
                        processedResponse = '<p>' + processedResponse + '</p>';
                    }

                    wsAssistantContentDiv.innerHTML = processedResponse;

                    allMessages.push({ 
                        content: wsResponseText, 
                        sender: 'assistant', 
                        element: wsAssistantMessageDiv 
                    });
                }

                if (currentThinkingContainer && !hasUsedTools) {
                    currentThinkingContainer.remove();
                    currentThinkingContainer = null;
                } else if (currentThinkingContainer) {
                    const thinkingHeader = currentThinkingContainer.querySelector('.analyzing-text, .searching-text');
                    const loader = currentThinkingContainer.querySelector('.thinking-loader, .search-loader');
                    
                    if (thinkingHeader && seconds > 0) {
                        let completionText = '';
                        if (toolsUsed.has('WebSearch') && toolsUsed.size > 1) {
                            completionText = `Used ${toolsUsed.size} tools in ${seconds}s`;
                        } else if (toolsUsed.has('WebSearch')) {
                            completionText = `Searched for ${seconds}s`;
                        } else {
                            completionText = `Thought for ${seconds}s`;
                        }
                        
                        thinkingHeader.textContent = completionText;
                        thinkingHeader.classList.remove('analyzing-text', 'searching-text');
                    }

                    if (loader) {
                        loader.style.display = 'none';
                    }
                }

                hasUsedTools = false;
                toolsUsed.clear();
                
                setTimeout(loadChatHistory, 1000);
                break;

            case 'error':
                console.error('WebSocket Error:', parsed.message);
                isWaitingForResponse = false;
                document.getElementById('sendBtn').disabled = false;
                addMessage(`Error: ${parsed.message}`, 'assistant');
                responseStartTime = null;
                toolsUsed.clear();
                break;

            case 'pong':
                console.log('Pong received');
                break;
        }
    } catch (e) {
        console.error('Error parsing WebSocket message:', e, data);
    }
}