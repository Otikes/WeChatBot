import React from 'react'
import ReactDOM from 'react-dom/client'
import App from './App'
import './index.css'

// --- console easter egg ---
;(function () {
  const c = 'color:#38bdf8;font-size:14px;'
  const b = 'color:#38bdf8;font-size:18px;font-weight:bold;'
  const n = 'color:#787774;font-size:12px;'
  console.log('%c◆%c  WeChatBot %c— 让群聊有个会做笔记的搭子', b, b, n)
  console.log('%c  二次开发自 GuMu599/webot · MIT', c)
})()

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
)
