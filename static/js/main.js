// Main client-side javascript for choloka.ge

document.addEventListener('DOMContentLoaded', function() {
    initNotifications();
    setupAlertsAutoClose();
});

// Notifications Polling and Panel logic
function initNotifications() {
    const bellBtn = document.getElementById('notif-bell-btn');
    const dropdown = document.getElementById('notif-dropdown');
    const countBadge = document.getElementById('notif-count');
    const itemsList = document.getElementById('notif-items-list');
    const markReadBtn = document.getElementById('mark-all-read-btn');

    if (!bellBtn) return; // Exit if user not logged in

    // Toggle dropdown
    bellBtn.addEventListener('click', function(e) {
        e.stopPropagation();
        const isVisible = dropdown.style.display === 'block';
        dropdown.style.display = isVisible ? 'none' : 'block';
        
        if (!isVisible) {
            // Position dropdown to the right of sidebar, aligned vertically with the bell
            const bellRect = bellBtn.getBoundingClientRect();
            dropdown.style.top = Math.max(10, bellRect.top) + 'px';
            // Fetch fresh notifications
            fetchNotifications();
        }
    });

    // Close dropdown on clicking outside
    document.addEventListener('click', function() {
        dropdown.style.display = 'none';
    });

    dropdown.addEventListener('click', function(e) {
        e.stopPropagation(); // Prevent closing when clicking inside dropdown
    });

    // Mark all as read
    if (markReadBtn) {
        markReadBtn.addEventListener('click', async function() {
            try {
                const response = await fetch('/api/notifications/read', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                if (response.ok) {
                    countBadge.style.display = 'none';
                    countBadge.textContent = '0';
                    itemsList.innerHTML = `
                        <div class="notification-item" style="color: var(--text-muted); text-align: center; padding: 20px;">
                            ახალი შეტყობინებები არ არის
                        </div>
                    `;
                }
            } catch (e) {
                console.error("Could not mark notifications read", e);
            }
        });
    }

    // Fetch notifications function
    async function fetchNotifications() {
        try {
            const response = await fetch('/api/notifications');
            if (response.ok) {
                const notifications = await response.json();
                
                if (notifications.length > 0) {
                    countBadge.textContent = notifications.length;
                    countBadge.style.display = 'flex';
                    
                    itemsList.innerHTML = '';
                    notifications.forEach(n => {
                        const item = document.createElement('div');
                        item.className = 'notification-item';
                        item.innerHTML = `
                            <div>${n.content}</div>
                            <div class="time"><i class="fa-regular fa-clock"></i> ${n.created_at}</div>
                        `;
                        itemsList.appendChild(item);
                    });
                } else {
                    countBadge.style.display = 'none';
                    itemsList.innerHTML = `
                        <div class="notification-item" style="color: var(--text-muted); text-align: center; padding: 20px;">
                            ახალი შეტყობინებები არ არის
                        </div>
                    `;
                }
            }
        } catch (e) {
            console.error("Error fetching notifications", e);
        }
    }

    // Run once on load
    fetchNotifications();

    // Poll for notifications every 6 seconds
    setInterval(fetchNotifications, 6000);
}

// Fade out alerts after 5 seconds
function setupAlertsAutoClose() {
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        setTimeout(() => {
            alert.style.transition = 'opacity 0.5s ease-out, transform 0.5s ease-out';
            alert.style.opacity = '0';
            alert.style.transform = 'translateY(-10px)';
            setTimeout(() => {
                alert.remove();
            }, 500);
        }, 5000);
    });
}

// Toggle post options dropdown
function togglePostDropdown(event, postId) {
    event.stopPropagation();
    
    // Close any other open post dropdowns first
    const openDropdowns = document.querySelectorAll('.post-options-dropdown');
    openDropdowns.forEach(dropdown => {
        if (dropdown.id !== `post-dropdown-${postId}`) {
            dropdown.style.display = 'none';
        }
    });

    const dropdown = document.getElementById(`post-dropdown-${postId}`);
    if (dropdown) {
        const isVisible = dropdown.style.display === 'block';
        dropdown.style.display = isVisible ? 'none' : 'block';
    }
}

// Close post dropdowns when clicking anywhere outside
document.addEventListener('click', function() {
    const openDropdowns = document.querySelectorAll('.post-options-dropdown');
    openDropdowns.forEach(dropdown => {
        dropdown.style.display = 'none';
    });
});

// Toggle like on a post via AJAX
async function likePost(postId) {
    const likeBtn = document.getElementById(`like-btn-${postId}`);
    if (!likeBtn) return;
    
    const likeCount = document.getElementById(`like-count-${postId}`);
    const likeIcon = likeBtn.querySelector('i');
    
    try {
        const response = await fetch(`/post/${postId}/like`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            
            // Update UI
            likeCount.textContent = data.likes_count;
            if (data.liked) {
                likeBtn.classList.add('liked');
                likeIcon.className = 'fa-solid fa-heart';
            } else {
                likeBtn.classList.remove('liked');
                likeIcon.className = 'fa-regular fa-heart';
            }
        }
    } catch (e) {
        console.error("Error liking post:", e);
    }
}

// Toggle comments drawer visibility
function toggleComments(postId) {
    const drawer = document.getElementById(`comments-drawer-${postId}`);
    if (drawer) {
        const isVisible = drawer.style.display === 'block';
        drawer.style.display = isVisible ? 'none' : 'block';
    }
}

// Share Modal Management
function openShareModal(postId, postTitle) {
    const overlay = document.getElementById('share-modal-overlay');
    const form = document.getElementById('share-form');
    const preview = document.getElementById('share-preview-title');
    const textarea = document.getElementById('share-comment-textarea');
    
    if (overlay && form && preview) {
        form.action = `/post/${postId}/share`;
        preview.textContent = `გაზიარება: "${postTitle}"`;
        if (textarea) textarea.value = '';
        overlay.style.display = 'flex';
    }
}

function closeShareModal() {
    const overlay = document.getElementById('share-modal-overlay');
    if (overlay) {
        overlay.style.display = 'none';
    }
}


// Toggle Follow Status
async function toggleFollow(userId) {
    const btn = document.getElementById('follow-btn');
    const isFollowing = btn.innerText.trim() === 'Unfollow';
    const endpoint = isFollowing ? '/unfollow/' : '/follow/';
    
    try {
        const response = await fetch(endpoint + userId, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'success') {
                if (isFollowing) {
                    btn.innerText = 'Follow';
                    btn.classList.remove('btn-secondary');
                    btn.classList.add('btn-primary');
                } else {
                    btn.innerText = 'Unfollow';
                    btn.classList.remove('btn-primary');
                    btn.classList.add('btn-secondary');
                }
                document.getElementById('followers-count').innerText = data.followers_count;
            }
        } else {
            const data = await response.json();
            alert(data.error || 'მოხდა შეცდომა');
        }
    } catch (error) {
        console.error('Error toggling follow:', error);
    }
}

// Delete Direct Message
async function deleteMessage(messageId) {
    if (!confirm('ნამდვილად გსურთ ამ მესიჯის წაშლა?')) return;
    
    try {
        const response = await fetch('/message/' + messageId + '/delete', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (response.ok) {
            const data = await response.json();
            if (data.status === 'success') {
                const msgContent = document.getElementById('msg-content-' + messageId);
                if (msgContent) {
                    msgContent.innerHTML = '<i>მესიჯი წაშლილია</i>';
                }
                
                const deleteBtn = document.getElementById('msg-delete-btn-' + messageId);
                if (deleteBtn) {
                    deleteBtn.remove();
                }
            }
        } else {
            const data = await response.json();
            alert(data.error || 'მოხდა შეცდომა მესიჯის წაშლისას');
        }
    } catch (error) {
        console.error('Error deleting message:', error);
    }
}
