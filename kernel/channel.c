// SPDX-License-Identifier: GPL-2.0-only
/* Bounded ioctl delivery with retained exact command results across reconnect. */
#include <linux/errno.h>
#include <linux/fs.h>
#include <linux/overflow.h>
#include <linux/slab.h>
#include <linux/string.h>
#include <linux/uaccess.h>
#include <linux/vmalloc.h>

#include "channel.h"
#include "control.h"

static int channel_open(struct inode *inode, struct file *file)
{
	struct miscdevice *device = file->private_data;
	struct kd_jit_channel *channel = container_of(device, struct kd_jit_channel, device);
	struct module *owner = channel->owner;
	bool old_hold = false;
	int result = 0;

	nonseekable_open(inode, file);
	/* misc_open serializes this callback against misc_deregister. */
	if (!try_module_get(owner))
		return -ENODEV;
	mutex_lock(&channel->guard);
	if (channel->closing || !channel->registered)
		result = -ENODEV;
	else if (channel->opened)
		result = -EBUSY;
	else {
		old_hold = channel->retained;
		channel->retained = false;
		channel->opened = true;
		file->private_data = channel;
	}
	mutex_unlock(&channel->guard);
	if (result || old_hold)
		module_put(owner);
	return result;
}

static int channel_release(struct inode *inode, struct file *file)
{
	struct kd_jit_channel *channel = file->private_data;
	struct module *owner = channel->owner;
	bool keep;

	(void)inode;
	mutex_lock(&channel->guard);
	/* File release cannot refuse close. Preserve the actual control session
	 * and its module hold instead of losing pending claims or receipts.
	 */
	keep = !kd_jit_control_session_idle(channel->session);
	channel->retained = keep;
	channel->opened = false;
	mutex_unlock(&channel->guard);
	/* Static core fops and callback code remain valid after this final access. */
	if (!keep)
		module_put(owner);
	return 0;
}

static int deliver(struct kd_jit_channel *channel, struct kd_control_exchange *request,
		  void __user *header)
{
	size_t length = channel->output_length;

	request->output_length = length;
	request->status = channel->status;
	if (length > request->output_capacity) {
		if (copy_to_user(header, request, sizeof(*request)))
			return -EFAULT;
		return -EMSGSIZE;
	}
	if ((length && copy_to_user(u64_to_user_ptr(request->output), channel->output, length)) ||
	    copy_to_user(header, request, sizeof(*request)))
		return -EFAULT;
	return 0;
}

static int query(struct kd_jit_channel *channel, struct kd_control_exchange *request,
		 void __user *header)
{
	u64 words[6];
	unsigned char __user *output = u64_to_user_ptr(request->output);
	size_t length;

	if (request->sequence || request->input_length)
		return -EINVAL;
	if (check_add_overflow(sizeof(words), channel->input_length, &length) ||
	    check_add_overflow(length, channel->output_length, &length))
		return -EOVERFLOW;
	request->output_length = length;
	request->status = 0;
	if (length > request->output_capacity) {
		if (copy_to_user(header, request, sizeof(*request)))
			return -EFAULT;
		return -EMSGSIZE;
	}
	words[0] = cpu_to_le64(KD_CONTROL_ABI);
	words[1] = cpu_to_le64(channel->operation);
	words[2] = cpu_to_le64(channel->sequence);
	words[3] = cpu_to_le64((u64)channel->status);
	words[4] = cpu_to_le64(channel->input_length);
	words[5] = cpu_to_le64(channel->output_length);
	if (copy_to_user(output, words, sizeof(words)) ||
	    (channel->input_length && copy_to_user(output + sizeof(words),
		channel->input, channel->input_length)) ||
	    (channel->output_length && copy_to_user(output + sizeof(words) + channel->input_length,
		channel->output, channel->output_length)) || copy_to_user(header, request, sizeof(*request)))
		return -EFAULT;
	return 0;
}

static long channel_ioctl(struct file *file, unsigned int command, unsigned long argument)
{
	struct kd_jit_channel *channel = file->private_data;
	struct kd_control_exchange request;
	void __user *header = (void __user *)argument;
	unsigned char *old_input;
	size_t output_length = 0;
	int result, status;

	if (command != KD_CONTROL_EXCHANGE)
		return -ENOTTY;
	if (copy_from_user(&request, header, sizeof(request)))
		return -EFAULT;
	if (request.abi != KD_CONTROL_ABI || request.input_length > channel->frame_capacity)
		return -EINVAL;
	mutex_lock(&channel->guard);
	if (channel->closing || !channel->opened) {
		result = -ENODEV;
		goto out;
	}
	if (request.operation == KD_CONTROL_QUERY) {
		result = query(channel, &request, header);
		goto out;
	}
	if (!request.sequence ||
	    (channel->cached && request.sequence != channel->sequence &&
	     (channel->sequence == U64_MAX || request.sequence != channel->sequence + 1)) ||
	    (!channel->cached && request.sequence != 1)) {
		result = -ESTALE;
		goto out;
	}
	if (request.input_length && copy_from_user(channel->next_input,
			u64_to_user_ptr(request.input), request.input_length)) {
		result = -EFAULT;
		goto out;
	}
	if (channel->cached && request.sequence == channel->sequence) {
		if (request.operation != channel->operation || request.input_length != channel->input_length ||
		    memcmp(channel->next_input, channel->input, channel->input_length)) {
			result = -ESTALE;
			goto out;
		}
		result = deliver(channel, &request, header);
		goto out;
	}
	/* All reply capacity is reserved before dispatch. A later user-copy
	 * failure retains the exact result and cannot repeat control effects.
	 */
	status = kd_jit_control_command(channel->session, request.operation,
		channel->next_input, request.input_length, channel->output,
		channel->frame_capacity, &output_length);
	if (output_length > channel->frame_capacity) {
		/* The provider violated its bounded output contract. Keep the exact
		 * command consumed; never retry a possibly completed effect here.
		 */
		status = -EOVERFLOW;
		output_length = 0;
	}
	old_input = channel->input;
	channel->input = channel->next_input;
	channel->next_input = old_input;
	channel->input_length = request.input_length;
	channel->output_length = output_length;
	channel->operation = request.operation;
	channel->sequence = request.sequence;
	channel->status = status;
	channel->cached = true;
	result = deliver(channel, &request, header);
out:
	mutex_unlock(&channel->guard);
	return result;
}

static const struct file_operations channel_operations = {
	.owner = THIS_MODULE,
	.open = channel_open,
	.release = channel_release,
	.unlocked_ioctl = channel_ioctl,
};

int kd_jit_channel_register(struct kd_jit_channel *channel, const char *name,
		struct module *owner, struct kd_jit_control_session *session,
		size_t frame_capacity)
{
	unsigned char *input, *next_input, *output;
	int result;

	if (!channel || !name || !*name || !session || !frame_capacity ||
	    frame_capacity > (SIZE_MAX - 6 * sizeof(u64)) / 2)
		return -EINVAL;
	input = kvmalloc(frame_capacity, GFP_KERNEL);
	next_input = kvmalloc(frame_capacity, GFP_KERNEL);
	output = kvmalloc(frame_capacity, GFP_KERNEL);
	if (!input || !next_input || !output) {
		result = -ENOMEM;
		goto free_buffers;
	}
	mutex_init(&channel->guard);
	channel->session = session;
	channel->owner = owner;
	channel->input = input;
	channel->next_input = next_input;
	channel->output = output;
	channel->frame_capacity = frame_capacity;
	channel->input_length = 0;
	channel->output_length = 0;
	channel->sequence = 0;
	channel->operation = 0;
	channel->status = 0;
	channel->cached = false;
	channel->opened = false;
	channel->retained = false;
	channel->closing = false;
	/* Registered is private until misc_register exposes this device. */
	channel->registered = true;
	channel->device.minor = MISC_DYNAMIC_MINOR;
	channel->device.name = name;
	channel->device.fops = &channel_operations;
	channel->device.parent = NULL;
	channel->device.groups = NULL;
	channel->device.nodename = NULL;
	channel->device.mode = 0600;
	result = misc_register(&channel->device);
	if (!result)
		return 0;
	channel->registered = false;
free_buffers:
	kvfree(output);
	kvfree(next_input);
	kvfree(input);
	return result;
}

int kd_jit_channel_unregister(struct kd_jit_channel *channel)
{
	struct module *owner;
	bool retained;

	if (!channel)
		return -EINVAL;
	mutex_lock(&channel->guard);
	if (!channel->registered || channel->closing) {
		mutex_unlock(&channel->guard);
		return -EALREADY;
	}
	if (channel->opened || !kd_jit_control_session_idle(channel->session)) {
		mutex_unlock(&channel->guard);
		return -EBUSY;
	}
	channel->closing = true;
	owner = channel->owner;
	retained = channel->retained;
	channel->retained = false;
	mutex_unlock(&channel->guard);
	misc_deregister(&channel->device);
	channel->registered = false;
	kvfree(channel->output);
	kvfree(channel->next_input);
	kvfree(channel->input);
	/* No provider/channel access after its final retained module release. */
	if (retained)
		module_put(owner);
	return 0;
}

EXPORT_SYMBOL_GPL(kd_jit_channel_register);
EXPORT_SYMBOL_GPL(kd_jit_channel_unregister);
