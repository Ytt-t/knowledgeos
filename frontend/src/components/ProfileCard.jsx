import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { getMe } from '../api'

// V8: 个人信息卡（点头像弹出：背景图 + 头像 + 昵称 + 个性签名 + 数据）
export default function ProfileCard({ onClose }) {
  const navigate = useNavigate()
  const [me, setMe] = useState(null)

  useEffect(() => {
    getMe().then(setMe).catch(() => {})
  }, [])

  return (
    <div className="fixed inset-0 bg-black/20 flex items-center justify-center z-50 p-4" onClick={onClose}>
      <div
        className="bg-white rounded-2xl shadow-2xl border border-neutral-100 w-full max-w-sm overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 背景图横幅 */}
        <div className="relative h-28 bg-neutral-50">
          {me?.banner_url && (
            <img src={me.banner_url} alt="" className="w-full h-full object-cover" />
          )}
        </div>

        <div className="px-6 pb-6 -mt-10 relative">
          {/* 头像 */}
          <div className="w-20 h-20 rounded-full border-4 border-white bg-neutral-100 overflow-hidden shadow flex items-center justify-center text-3xl text-neutral-400">
            {me?.avatar_url ? (
              <img src={me.avatar_url} alt="" className="w-full h-full object-cover" />
            ) : (
              <span>{(me?.nickname || '学')[0]}</span>
            )}
          </div>

          <h2 className="text-lg font-semibold text-neutral-900 mt-3">
            {me?.nickname || '默认用户'}
          </h2>

          {me?.signature && (
            <p className="text-xs text-neutral-500 mt-1.5 leading-relaxed">{me.signature}</p>
          )}
          {me?.email && (
            <p className="text-xs text-neutral-400 mt-1">{me.email}</p>
          )}

          {/* 数据统计 */}
          <div className="grid grid-cols-3 divide-x divide-neutral-100 border border-neutral-100 rounded-xl mt-5">
            <div className="py-3 text-center">
              <div className="text-base font-semibold text-neutral-900">{me?.total_cards || 0}</div>
              <div className="text-[10px] text-neutral-400 mt-0.5">知识</div>
            </div>
            <div className="py-3 text-center">
              <div className="text-base font-semibold text-neutral-900">{me?.review_count || 0}</div>
              <div className="text-[10px] text-neutral-400 mt-0.5">复习</div>
            </div>
            <div className="py-3 text-center">
              <div className="text-base font-semibold text-neutral-900">
                {me?.has_password ? '已设' : '未设'}
              </div>
              <div className="text-[10px] text-neutral-400 mt-0.5">密码</div>
            </div>
          </div>

          {me?.bio && (
            <p className="text-xs text-neutral-500 mt-4 leading-relaxed bg-neutral-50 rounded-lg px-3.5 py-2.5">
              {me.bio}
            </p>
          )}

          <button
            onClick={() => { onClose(); navigate('/settings') }}
            className="w-full mt-5 py-2.5 text-sm border border-neutral-200 text-neutral-700 rounded-lg hover:bg-neutral-50 transition"
          >
            编辑资料
          </button>
        </div>
      </div>
    </div>
  )
}
