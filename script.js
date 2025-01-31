import { SSE } from './sse.js';

const thinkingIndicator = document.getElementById('thinking-indicator');
thinkingIndicator.style.display = 'none';
const sendbtn = document.getElementById('sendbtn');
const textarea = document.querySelector('.textarea');
const systemPrompt = `You're a smart mature woman named Sakura, keep your replies ,humble,polite,respectful and reply within 1 short statement, use emoticons to express emotions`;
let msgHistory = [
    { "role": "system", "content": systemPrompt }
];
sendbtn.addEventListener('click', () => {
    if (textarea.value === '') return;
    thinkingIndicator.style.display = 'block';
    document.getElementById('sendbtn').disabled = true;
    const msg = textarea.value + '';
    document.getElementById('chatmsg').value = '';
    document.getElementById('chatmsg').disabled = true;
    document.getElementById('sdbtn').disabled = true;
    const chatContainer = document.getElementById('chat-container');
    const newChat = document.createElement('div');
    newChat.classList.add('chat', 'chat-end');
    const chatBubble = document.createElement('div');
    chatBubble.classList.add('chat-bubble','bg-purple-900','text-white', 'my-1');
    chatBubble.textContent = msg;
    newChat.appendChild(chatBubble);
    chatContainer.appendChild(newChat);
    msgHistory.push({ "role": "user", "content": msg });
    newChat.scrollIntoView({ behavior: 'smooth' });
    getResponse();
});

function getResponse() {
    const url = "https://noob2.dhanushpchande.workers.dev/"
    let msgjson = {
        "messages": msgHistory
    }
    msgjson = (JSON.stringify(msgjson));
    const source = new SSE(url, {
        headers: {
            'Content-Type': 'text/plain'
        },
        payload: msgjson
    });
    const chatContainer = document.getElementById('chat-container');
    const newChat = document.createElement('div');
    newChat.classList.add('chat', 'chat-start');
    const chatHeader = document.createElement('div');
    chatHeader.classList.add('chat-header');
    chatHeader.textContent = 'Sakura';
    const chatBubble = document.createElement('div');
    chatBubble.classList.add('chat-bubble','bg-purple-900','text-white');
    newChat.appendChild(chatHeader);
    newChat.appendChild(chatBubble);
    let childAppend = false;
    source.onmessage = (event) => {
        if (event.data === "[DONE]") {
            source.close();
            msgHistory.push({ role: "assistant", content: chatBubble.textContent });
            document.getElementById('sendbtn').disabled = false;
            document.getElementById('chatmsg').disabled = false;
            document.getElementById('sdbtn').disabled = false;
            return
        }
        const data = JSON.parse(event.data);
        if (!childAppend) {
            thinkingIndicator.style.display = 'none';
            chatContainer.appendChild(newChat);
            childAppend = true;
        }
        chatBubble.textContent += data.response;
        chatBubble.scrollIntoView({ behavior: 'smooth' })
    }
}

const sdbtn = document.getElementById('sdbtn');
sdbtn.addEventListener('click', async () => {
    if (textarea.value === '') return;
    thinkingIndicator.style.display = 'block';
    document.getElementById('sendbtn').disabled = true;
    const msg = textarea.value + '';
    document.getElementById('chatmsg').value = '';
    document.getElementById('chatmsg').disabled = true;
    document.getElementById('sdbtn').disabled = true;
    const chatContainer = document.getElementById('chat-container');
    const newChat = document.createElement('div');
    newChat.classList.add('chat', 'chat-end');
    const chatBubble = document.createElement('div');
    chatBubble.classList.add('chat-bubble','bg-purple-900','text-white', 'my-1');
    chatBubble.textContent = msg;
    newChat.appendChild(chatBubble);
    chatContainer.appendChild(newChat);
    newChat.scrollIntoView({ behavior: 'smooth' });
    const diffusionURL = `https://noob.dhanushpchande.workers.dev/?prompt=${encodeURIComponent(msg)}`;
    let response = await fetch(diffusionURL);
    if (response.ok) {
        let imageBlob = await response.blob();
        let imageURL = URL.createObjectURL(imageBlob);
        let img = document.createElement('img');
        img.src = imageURL;
        img.classList.add('chat-image');
        const chatContainer = document.getElementById('chat-container');
        const newChat = document.createElement('div');
        newChat.classList.add('chat', 'chat-start');
        newChat.appendChild(img);
        chatContainer.appendChild(newChat);
        newChat.scrollIntoView({ behavior: 'smooth' });
        thinkingIndicator.style.display = 'none';
        document.getElementById('sendbtn').disabled = false;
        document.getElementById('chatmsg').disabled = false;
        document.getElementById('sdbtn').disabled = false;
    }
});

function submitOnEnter(event) {
    if (event.which === 13 && !event.shiftKey) {
        if (!event.repeat) {
            sendbtn.click();
        }

        event.preventDefault();
    }
}

document.getElementById("chatmsg").addEventListener("keypress", submitOnEnter);
